"""Server-sent events: every connected browser sees changes live."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..services.events import bus

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(request: Request):
    q = bus.listen()

    async def gen():
        try:
            yield {"event": "hello", "data": "{}"}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": ev.type, "data": ev.to_json()}
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unlisten(q)

    return EventSourceResponse(gen())
