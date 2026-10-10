"""Intake requests: stakeholder asks that the agent clarifies and turns into backlog."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..agent import _compat as c
from ..agent import intake as intake_agent
from ..db import utcnow
from ..models import IntakeMessage, IntakeRequest, Project, User
from ..schemas.common import IntakeRequestOut
from ..services.auth import DB, CurrentUser
from ..services.events import bus

log = logging.getLogger(__name__)
router = APIRouter(tags=["intake"])


class IntakeIn(BaseModel):
    subject: str
    body: str
    requester_name: str | None = None
    requester_email: str | None = None
    project_id: str | None = None
    channel: str | None = None


class IntakeMessageIn(BaseModel):
    body: str
    direction: str = "inbound"  # inbound | internal
    author: str | None = None


class ConvertIn(BaseModel):
    project_id: str
    parent_id: str | None = None
    items: list[dict[str, Any]] | None = None


class RejectIn(BaseModel):
    reason: str | None = None


class IntakePatch(BaseModel):
    owner_id: str | None = None
    project_id: str | None = None
    state: str | None = None
    max_questions: int | None = None


def _get(db, request_id: str) -> IntakeRequest:
    req = db.get(IntakeRequest, request_id)
    if req is None:
        raise HTTPException(404, "Intake request not found")
    return req


def _emit(req: IntakeRequest, actor: User | None = None, created: bool = False) -> None:
    bus.emit(
        "intake.created" if created else "intake.updated",
        project_id=req.project_id,
        entity_type="intake",
        entity_id=req.id,
        actor_id=actor.id if actor else None,
        data={"state": req.state, "needs_human": req.needs_human},
    )


@router.get("/intake", response_model=list[IntakeRequestOut])
def list_intake(db: DB, user: CurrentUser, state: str | None = None):
    stmt = select(IntakeRequest).order_by(IntakeRequest.last_activity_at.desc())
    if state:
        stmt = stmt.where(IntakeRequest.state == state)
    return db.scalars(stmt.limit(200)).all()


@router.get("/intake/{request_id}", response_model=IntakeRequestOut)
def get_intake(request_id: str, db: DB, user: CurrentUser):
    return _get(db, request_id)


@router.post("/intake", response_model=IntakeRequestOut, status_code=201)
async def create_intake(body: IntakeIn, db: DB, user: CurrentUser):
    if body.project_id and db.get(Project, body.project_id) is None:
        raise HTTPException(404, "Project not found")
    req = IntakeRequest(
        subject=body.subject.strip()[:300] or "(no subject)",
        original_body=body.body,
        requester_name=body.requester_name or user.name,
        requester_email=body.requester_email or user.email,
        project_id=body.project_id,
        channel=body.channel or "web",
        owner_id=user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    _emit(req, user, created=True)
    req_id = req.id
    db.close()
    try:
        await intake_agent.analyze(req_id)
    except Exception:
        log.exception("initial intake analysis failed")
    return _fresh(db, req_id)


def _fresh(db, request_id: str) -> IntakeRequest:
    db.expire_all()
    return _get(db, request_id)


@router.post("/intake/{request_id}/messages", response_model=IntakeRequestOut)
async def add_message(request_id: str, body: IntakeMessageIn, db: DB, user: CurrentUser):
    req = _get(db, request_id)
    direction = body.direction if body.direction in ("inbound", "internal") else "inbound"
    author = body.author or (req.requester_name or req.requester_email or "requester" if direction == "inbound" else user.name)
    db.add(IntakeMessage(request_id=req.id, direction=direction, author=author, body=body.body))
    req.last_activity_at = utcnow()
    db.commit()
    _emit(req, user)
    db.close()
    if direction == "inbound":
        try:
            await intake_agent.analyze(request_id)
        except Exception:
            log.exception("intake re-analysis failed")
    return _fresh(db, request_id)


@router.post("/intake/{request_id}/analyze", response_model=IntakeRequestOut)
async def analyze(request_id: str, db: DB, user: CurrentUser):
    _get(db, request_id)
    db.close()
    try:
        await intake_agent.analyze(request_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _fresh(db, request_id)


@router.post("/intake/{request_id}/convert")
def convert(request_id: str, body: ConvertIn, db: DB, user: CurrentUser):
    req = _get(db, request_id)
    if req.state == "converted":
        raise HTTPException(409, "Already converted")
    project = db.get(Project, body.project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    created = intake_agent.convert(db, req, project, body.parent_id, body.items, user)
    db.commit()
    for it in created:
        db.refresh(it)
    _emit(req, user)
    return [c.item_out(db, it) for it in created]


@router.post("/intake/{request_id}/reject", response_model=IntakeRequestOut)
def reject(request_id: str, body: RejectIn, db: DB, user: CurrentUser):
    req = _get(db, request_id)
    req.state = "rejected"
    req.last_activity_at = utcnow()
    db.add(
        IntakeMessage(
            request_id=req.id, direction="internal", author=user.name, body=f"Rejected: {body.reason or 'no reason given'}"
        )
    )
    db.commit()
    _emit(req, user)
    return req


@router.patch("/intake/{request_id}", response_model=IntakeRequestOut)
def patch(request_id: str, body: IntakePatch, db: DB, user: CurrentUser):
    req = _get(db, request_id)
    data = body.model_dump(exclude_unset=True)
    if "state" in data and data["state"] not in ("new", "clarifying", "ready", "converted", "rejected", "on_hold"):
        raise HTTPException(400, "Bad state")
    if data.get("project_id") and db.get(Project, data["project_id"]) is None:
        raise HTTPException(404, "Project not found")
    if data.get("owner_id") and db.get(User, data["owner_id"]) is None:
        raise HTTPException(404, "User not found")
    for k, v in data.items():
        setattr(req, k, v)
    req.last_activity_at = utcnow()
    db.commit()
    _emit(req, user)
    return req
