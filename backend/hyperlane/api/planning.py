"""Planning: capacity profiles, sprint capacity, plan suggestion/commit, retrospectives."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CapacityProfile, Project, Sprint, User
from ..schemas.common import SprintOut
from ..services import capacity
from ..services import retro as retro_service
from ..services.auth import DB, CurrentUser

router = APIRouter(tags=["planning"])


def _project(db: Session, pid: str) -> Project:
    project = db.get(Project, pid)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _sprint(db: Session, sid: str) -> Sprint:
    sprint = db.get(Sprint, sid)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    return sprint


# ---- capacity ----


class CapacityEntryIn(BaseModel):
    user_id: str
    days_off: float = 0.0
    available_hours: float | None = None
    notes: str | None = None


class CapacityIn(BaseModel):
    entries: list[CapacityEntryIn]


class CommitIn(BaseModel):
    item_ids: list[str] = Field(default_factory=list)


@router.get("/projects/{pid}/capacity")
def project_capacity(pid: str, db: DB, _: CurrentUser):
    project = _project(db, pid)
    profiles = list(db.scalars(select(CapacityProfile).where(CapacityProfile.project_id == project.id)))
    return [capacity.profile_to_dict(p, db.get(User, p.user_id)) for p in profiles]


@router.get("/sprints/{sid}/capacity")
def sprint_capacity(sid: str, db: DB, _: CurrentUser):
    return capacity.sprint_capacity(db, _sprint(db, sid))


@router.put("/sprints/{sid}/capacity")
def put_sprint_capacity(sid: str, body: CapacityIn, db: DB, _: CurrentUser):
    entries = [e.model_dump(exclude_unset=True) for e in body.entries]
    return capacity.upsert_entries(db, _sprint(db, sid), entries)


@router.get("/sprints/{sid}/plan/suggest")
def plan_suggest(sid: str, db: DB, _: CurrentUser):
    return capacity.suggest_plan(db, _sprint(db, sid))


@router.post("/sprints/{sid}/plan/commit", response_model=SprintOut)
def plan_commit(sid: str, body: CommitIn, db: DB, user: CurrentUser):
    return capacity.commit_plan(db, _sprint(db, sid), body.item_ids, actor=user)


# ---- retro ----


class RetroPatch(BaseModel):
    went_well: list[dict[str, Any]] | None = None
    improve: list[dict[str, Any]] | None = None
    kudos: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    mood: dict[str, int] | None = None
    agent_summary: str | None = None
    facilitator_id: str | None = None


class RetroItemIn(BaseModel):
    column: Literal["went_well", "improve", "kudos", "actions"]
    text: str
    owner_id: str | None = None


class RetroVoteIn(BaseModel):
    column: Literal["went_well", "improve", "kudos"]
    entry_id: str


class RetroMoodIn(BaseModel):
    score: int = Field(ge=1, le=5)


@router.get("/sprints/{sid}/retro")
def get_retro(sid: str, db: DB, user: CurrentUser):
    return retro_service.to_dict(retro_service.get_or_create(db, _sprint(db, sid), user))


@router.put("/sprints/{sid}/retro")
def put_retro(sid: str, body: RetroPatch, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.update(db, r, body.model_dump(exclude_unset=True), user))


@router.post("/sprints/{sid}/retro/items")
def post_retro_item(sid: str, body: RetroItemIn, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.add_item(db, r, body.column, body.text, user, owner_id=body.owner_id))


@router.post("/sprints/{sid}/retro/vote")
def post_retro_vote(sid: str, body: RetroVoteIn, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.vote(db, r, body.column, body.entry_id, user))


@router.post("/sprints/{sid}/retro/mood")
def post_retro_mood(sid: str, body: RetroMoodIn, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.mood(db, r, user, body.score))


@router.post("/sprints/{sid}/retro/generate")
def post_retro_generate(sid: str, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.generate_summary(db, r, user))


@router.post("/sprints/{sid}/retro/close")
def post_retro_close(sid: str, db: DB, user: CurrentUser):
    r = retro_service.get_or_create(db, _sprint(db, sid), user)
    return retro_service.to_dict(retro_service.close(db, r, user))
