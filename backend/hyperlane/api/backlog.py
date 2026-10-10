"""Prompt-driven backlog builder: generate a proposal, then apply it as real items."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agent import _compat as c
from ..agent import backlog
from ..agent.provider import ProviderError
from ..models import Project
from ..schemas.common import BacklogProposalOut
from ..services.auth import DB, CurrentUser

router = APIRouter(tags=["backlog"])


class GenerateIn(BaseModel):
    prompt: str
    parent_id: str | None = None


class ApplyIn(BaseModel):
    items: list[dict[str, Any]]
    parent_id: str | None = None


def _project(db, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/projects/{project_id}/backlog/generate", response_model=BacklogProposalOut)
async def generate(project_id: str, body: GenerateIn, db: DB, user: CurrentUser):
    project = _project(db, project_id)
    if not body.prompt.strip():
        raise HTTPException(400, "Tell me what to build first")
    try:
        return await backlog.propose(db, project, body.prompt, body.parent_id, user)
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/projects/{project_id}/backlog/apply")
def apply(project_id: str, body: ApplyIn, db: DB, user: CurrentUser):
    project = _project(db, project_id)
    if not body.items:
        raise HTTPException(400, "Nothing to apply")
    created = backlog.apply(db, project, body.items, body.parent_id, user)
    db.commit()
    for it in created:
        db.refresh(it)
    return [c.item_out(db, it) for it in created]
