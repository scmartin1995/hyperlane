"""Workspace settings, templates, health, onboarding state."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__
from ..config import get_settings
from ..models import Project, User, Workspace
from ..schemas.common import WorkspaceOut
from ..services.auth import DB
from ..services.events import bus
from ..services.templates import list_templates

router = APIRouter(tags=["workspace"])


class WorkspaceIn(BaseModel):
    name: str | None = None
    tagline: str | None = None
    theme: str | None = None
    flavor: bool | None = None
    onboarded: bool | None = None
    settings: dict | None = None


@router.get("/health")
def health(db: DB):
    s = get_settings()
    ws = db.get(Workspace, "default")
    return {
        "ok": True,
        "version": __version__,
        "onboarded": bool(ws and ws.onboarded),
        "profiles": db.query(User).count(),
        "projects": db.query(Project).count(),
        "llm": {"provider": s.llm_provider, "model": s.llm_model, "configured": _llm_configured(s)},
        "slack": s.slack_enabled,
        "teams": s.teams_enabled,
        "email_intake": s.email_intake_enabled,
    }


def _llm_configured(s) -> bool:
    if s.llm_provider == "anthropic":
        return bool(s.anthropic_api_key) or True  # may also use an `ant auth login` profile
    if s.llm_provider == "bedrock":
        return bool(s.aws_region)
    if s.llm_provider == "claude-code":
        import shutil

        return shutil.which("claude") is not None
    return False


@router.get("/workspace", response_model=WorkspaceOut)
def get_workspace(db: DB):
    return db.get(Workspace, "default")


@router.patch("/workspace", response_model=WorkspaceOut)
def update_workspace(body: WorkspaceIn, db: DB):
    ws = db.get(Workspace, "default")
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "settings":
            ws.settings = {**(ws.settings or {}), **v}
        else:
            setattr(ws, k, v)
    db.commit()
    bus.emit("workspace.updated", entity_type="workspace", entity_id="default")
    return ws


@router.get("/templates")
def templates():
    return list_templates()
