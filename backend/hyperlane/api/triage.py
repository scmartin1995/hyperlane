"""Triage: requests surface in the backlog; actions live on the item."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models import WorkItem
from ..services import triage
from ..services.auth import DB, CurrentUser
from ..services.items import serialize_item

router = APIRouter(tags=["triage"])


class TriageIn(BaseModel):
    action: str  # accept | escalate | decline | snooze
    type: str | None = None
    sprint_id: str | None = None
    until: date | None = None
    reason: str | None = None
    create_children: bool = True


class MessageIn(BaseModel):
    body: str


@router.get("/projects/{pid}/triage")
def list_triage(pid: str, db: DB, _: CurrentUser, include_snoozed: bool = True):
    return triage.list_triage(db, pid, include_snoozed=include_snoozed)


@router.post("/items/{item_id}/triage")
def triage_item(item_id: str, body: TriageIn, db: DB, user: CurrentUser):
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    created: list[WorkItem] = []
    if body.action == "accept":
        created = triage.accept(db, item, user, type=body.type, create_children=body.create_children)
    elif body.action == "escalate":
        created = triage.escalate(db, item, user, sprint_id=body.sprint_id, type=body.type)
    elif body.action == "decline":
        triage.decline(db, item, user, body.reason)
    elif body.action == "snooze":
        if body.until is None:
            raise HTTPException(400, "until is required to snooze")
        triage.snooze(db, item, user, body.until)
    else:
        raise HTTPException(400, f"Unknown action {body.action}")
    db.commit()
    db.refresh(item)
    return {"item": serialize_item(item, db), "created": [serialize_item(c, db) for c in created]}


@router.post("/items/{item_id}/message-requester")
def message_requester(item_id: str, body: MessageIn, db: DB, user: CurrentUser):
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    if not body.body.strip():
        raise HTTPException(400, "Message is empty")
    triage.message_requester(db, item, body.body.strip(), user)
    db.commit()
    db.refresh(item)
    return serialize_item(item, db)
