"""Work items: list/tree/create/bulk, detail, patch, move, bulk-update, archive, activity, transitions, comments."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import Comment, WorkItem
from ..schemas.common import ActivityOut, CommentOut, StatusTransitionOut, WorkItemOut
from ..schemas.core import (
    BulkCreateIn,
    BulkUpdateIn,
    CommentIn,
    CommentPatch,
    MoveIn,
    MoveOut,
    WorkItemIn,
    WorkItemPatch,
)
from ..services import items as svc
from ..services.activity import list_activity
from ..services.auth import DB, CurrentUser
from .projects import get_project

router = APIRouter(tags=["items"])


def get_item(db, item_id: str) -> WorkItem:
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


def _get_comment(db, comment_id: str) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(404, "Comment not found")
    return comment


# ---- per project ----


@router.get("/projects/{project_id}/items", response_model=list[WorkItemOut])
def list_items(
    project_id: str,
    db: DB,
    type: str | None = None,
    status: str | None = None,
    category: str | None = None,
    sprint_id: str | None = None,
    assignee_id: str | None = None,
    parent_id: str | None = None,
    q: str | None = None,
    label: str | None = None,
    unscheduled: bool = False,
    include_archived: bool = False,
    include_done: bool = True,
    limit: int | None = None,
):
    get_project(db, project_id)
    items = svc.list_items(
        db, project_id, type=type, status=status, category=category, sprint_id=sprint_id, assignee_id=assignee_id,
        parent_id=parent_id, q=q, label=label, unscheduled=unscheduled, include_archived=include_archived,
        include_done=include_done, limit=limit,
    )  # fmt: skip
    return svc.serialize_items(items, db)


@router.get("/projects/{project_id}/items/tree")
def item_tree(project_id: str, db: DB, include_done: bool = True):
    get_project(db, project_id)
    return svc.item_tree(db, project_id, include_done=include_done)


@router.post("/projects/{project_id}/items", response_model=WorkItemOut, status_code=201)
def create_item(project_id: str, body: WorkItemIn, db: DB, user: CurrentUser):
    item = svc.create_item(db, get_project(db, project_id), body.model_dump(exclude_unset=True), user)
    return svc.serialize_item(item, db)


@router.post("/projects/{project_id}/items/bulk", response_model=list[WorkItemOut], status_code=201)
def bulk_create(project_id: str, body: BulkCreateIn, db: DB, user: CurrentUser):
    project = get_project(db, project_id)
    items = svc.bulk_create(db, project, [i.model_dump(exclude_unset=True) for i in body.items], user)
    return svc.serialize_items(items, db)


# ---- single items ----


@router.post("/items/bulk-update", response_model=list[WorkItemOut])
def bulk_update(body: BulkUpdateIn, db: DB, user: CurrentUser):
    items = [get_item(db, i) for i in body.ids]
    updated = svc.bulk_update(db, items, body.patch.model_dump(exclude_unset=True), user)
    return svc.serialize_items(updated, db)


@router.get("/items/{item_id}")
def read_item(item_id: str, db: DB):
    return svc.serialize_detail(get_item(db, item_id), db)


@router.patch("/items/{item_id}", response_model=WorkItemOut)
def update_item(item_id: str, body: WorkItemPatch, db: DB, user: CurrentUser):
    item = svc.update_item(db, get_item(db, item_id), body.model_dump(exclude_unset=True), user)
    return svc.serialize_item(item, db)


@router.post("/items/{item_id}/move", response_model=MoveOut)
def move_item(item_id: str, body: MoveIn, db: DB, user: CurrentUser):
    data = body.model_dump(exclude_unset=True)
    item, warning = svc.move_item(
        db, get_item(db, item_id), status=data.get("status"),
        sprint_id=data.get("sprint_id", svc.UNSET),
        parent_id=data.get("parent_id", svc.UNSET),
        before_id=data.get("before_id"), after_id=data.get("after_id"), actor=user,
    )  # fmt: skip
    out = MoveOut.model_validate(svc.serialize_item(item, db).model_dump())
    out.wip_warning = warning
    return out


@router.delete("/items/{item_id}")
def delete_item(item_id: str, db: DB, user: CurrentUser, hard: bool = False):
    svc.archive_item(db, get_item(db, item_id), user, hard=hard)
    return {"ok": True, "hard": hard}


@router.get("/items/{item_id}/activity", response_model=list[ActivityOut])
def item_activity(item_id: str, db: DB, limit: int = 100):
    item = get_item(db, item_id)
    return list_activity(db, entity_type="work_item", entity_id=item.id, limit=min(limit, 500))


@router.get("/items/{item_id}/transitions", response_model=list[StatusTransitionOut])
def item_transitions(item_id: str, db: DB):
    return svc.transitions(db, get_item(db, item_id))


# ---- comments ----


@router.post("/items/{item_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(item_id: str, body: CommentIn, db: DB, user: CurrentUser):
    comment = svc.add_comment(db, get_item(db, item_id), body.body, author=user, is_decision=body.is_decision)
    return svc.serialize_comment(comment)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def update_comment(comment_id: str, body: CommentPatch, db: DB, user: CurrentUser):
    comment = svc.update_comment(db, _get_comment(db, comment_id), body.model_dump(exclude_unset=True), user)
    return svc.serialize_comment(comment)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: DB, user: CurrentUser):
    svc.delete_comment(db, _get_comment(db, comment_id), user)
    return {"ok": True}
