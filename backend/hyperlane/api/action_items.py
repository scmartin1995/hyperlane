"""Private action items + the personal overview. Everything here is scoped to the logged-in user."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..models import Project, Sprint
from ..schemas.common import ActionItemOut, SprintOut
from ..schemas.core import ActionItemIn, ActionItemPatch, ReorderIn
from ..services import action_items as svc
from ..services import items as items_svc
from ..services.auth import DB, CurrentUser

router = APIRouter(prefix="/me", tags=["me"])


def _mine(db, user, item_id: str):
    row = svc.get_action_item(db, user, item_id)
    if row is None:
        raise HTTPException(404, "Action item not found")  # never reveal another user's rows
    return row


@router.get("/action-items", response_model=list[ActionItemOut])
def list_action_items(db: DB, user: CurrentUser, include_done: bool = False):
    return svc.list_action_items(db, user, include_done=include_done)


@router.post("/action-items", response_model=ActionItemOut, status_code=201)
def create_action_item(body: ActionItemIn, db: DB, user: CurrentUser):
    return svc.create_action_item(db, user, body.model_dump(exclude_unset=True))


@router.post("/action-items/reorder", response_model=list[ActionItemOut])
def reorder(body: ReorderIn, db: DB, user: CurrentUser):
    return svc.reorder(db, user, body.ids)


@router.patch("/action-items/{item_id}", response_model=ActionItemOut)
def update_action_item(item_id: str, body: ActionItemPatch, db: DB, user: CurrentUser):
    return svc.update_action_item(db, user, _mine(db, user, item_id), body.model_dump(exclude_unset=True))


@router.delete("/action-items/{item_id}")
def delete_action_item(item_id: str, db: DB, user: CurrentUser):
    svc.delete_action_item(db, user, _mine(db, user, item_id))
    return {"ok": True}


@router.get("/overview")
def overview(db: DB, user: CurrentUser):
    assigned, in_progress = items_svc.my_items(db, user)
    open_count, overdue = svc.counts(db, user)
    sprints = db.scalars(
        select(Sprint).join(Project, Project.id == Sprint.project_id)
        .where(Sprint.state == "active", Project.status != "archived").order_by(Sprint.start_date)
    )  # fmt: skip
    return {
        "assigned": [o.model_dump(mode="json") for o in items_svc.serialize_items(assigned, db)],
        "in_progress": [o.model_dump(mode="json") for o in items_svc.serialize_items(in_progress, db)],
        "action_items_open": open_count,
        "action_items_overdue": overdue,
        "mentions": [items_svc.serialize_comment(c).model_dump(mode="json") for c in items_svc.mentions_for(db, user)],
        "active_sprints": [SprintOut.model_validate(s).model_dump(mode="json") for s in sprints],
    }
