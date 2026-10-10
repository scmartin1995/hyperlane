"""FastAPI application factory.

    uv run hyperlane            # production-ish: serves built frontend from frontend/dist
    uv run hyperlane --dev      # API only (Vite dev server proxies /api)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import collect_routers
from .config import get_settings
from .db import init_db
from .services import scheduler
from .services.events import bus

log = logging.getLogger("hyperlane")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    bus.bind_loop(asyncio.get_running_loop())
    from .services.bootstrap import ensure_workspace

    ensure_workspace()
    # integrations (Slack socket mode, email polling, notification router) start themselves if configured
    try:
        from .integrations import start_all

        start_all(app)
    except ImportError:
        log.info("integrations package not available yet")
    scheduler.start()
    log.info("Hyperlane %s ready", __version__)
    yield
    scheduler.stop()
    try:
        from .integrations import stop_all

        stop_all()
    except ImportError:
        pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Hyperlane", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

    for router in collect_routers():
        app.include_router(router, prefix="/api")

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    dist = Path(settings.frontend_dist)
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()


def run() -> None:
    import sys

    import uvicorn

    settings = get_settings()
    dev = "--dev" in sys.argv
    uvicorn.run(
        "hyperlane.main:app",
        host=settings.host,
        port=settings.port,
        reload=dev,
        reload_dirs=[str(Path(__file__).parent)] if dev else None,
        log_level="info",
    )


if __name__ == "__main__":
    run()
