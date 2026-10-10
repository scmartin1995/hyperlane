"""Private per-user action items. Every function is scoped to the owner; nothing here is shared."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import ActionItem, User
from .events import bus
from .items import PRIORITIES

_FIELDS = ("title", "notes", "due_date", "priority", "tags", "work_item_id", "project_id", "source", "source_ref",
           "snoozed_until")  # fmt: skip


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def list_action_items(db: Session, owner: User, include_done: bool = False) -> list[ActionItem]:
    stmt = select(ActionItem).where(ActionItem.owner_id == owner.id)
    if not include_done:
        stmt = stmt.where(ActionItem.done.is_(False))
    stmt = stmt.order_by(ActionItem.done.asc(), ActionItem.position.asc(), ActionItem.due_date.asc().nulls_last(),
                         ActionItem.created_at.asc())  # fmt: skip
    return list(db.scalars(stmt))


def get_action_item(db: Session, owner: User, item_id: str) -> ActionItem | None:
    """Owner-scoped lookup: returns None (not a different user's row) when it isn't theirs."""
    row = db.get(ActionItem, item_id)
    return row if row is not None and row.owner_id == owner.id else None


def create_action_item(db: Session, owner: User, data: dict[str, Any]) -> ActionItem:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    priority = data.get("priority") or "medium"
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
    last = db.scalar(select(func.max(ActionItem.position)).where(ActionItem.owner_id == owner.id)) or 0.0
    row = ActionItem(
        owner_id=owner.id,
        title=title[:300],
        notes=data.get("notes"),
        due_date=_to_date(data.get("due_date")),
        priority=priority,
        tags=list(data.get("tags") or []),
        work_item_id=data.get("work_item_id"),
        project_id=data.get("project_id"),
        source=data.get("source") or "manual",
        source_ref=data.get("source_ref"),
        snoozed_until=_to_date(data.get("snoozed_until")),
        position=float(last) + 1.0,
    )
    if data.get("done"):
        row.done, row.done_at = True, utcnow()
    db.add(row)
    db.commit()
    bus.emit("action_item.created", entity_type="action_item", entity_id=row.id, actor_id=owner.id,
             project_id=row.project_id)  # fmt: skip
    return row


def update_action_item(db: Session, owner: User, item: ActionItem, data: dict[str, Any]) -> ActionItem:
    if item.owner_id != owner.id:
        raise PermissionError("not your action item")
    for field in _FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "title":
            value = (value or "").strip()[:300]
            if not value:
                raise ValueError("title cannot be empty")
        elif field == "priority":
            value = value or "medium"
            if value not in PRIORITIES:
                raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
        elif field in ("due_date", "snoozed_until"):
            value = _to_date(value)
        elif field == "tags":
            value = list(value or [])
        elif field == "source":
            value = value or "manual"
        setattr(item, field, value)
    if "done" in data and data["done"] is not None and bool(data["done"]) != item.done:
        item.done = bool(data["done"])
        item.done_at = utcnow() if item.done else None
    if "position" in data and data["position"] is not None:
        item.position = float(data["position"])
    item.updated_at = utcnow()
    db.commit()
    bus.emit("action_item.updated", entity_type="action_item", entity_id=item.id, actor_id=owner.id,
             project_id=item.project_id)  # fmt: skip
    return item


def delete_action_item(db: Session, owner: User, item: ActionItem) -> None:
    if item.owner_id != owner.id:
        raise PermissionError("not your action item")
    iid = item.id
    db.delete(item)
    db.commit()
    bus.emit("action_item.deleted", entity_type="action_item", entity_id=iid, actor_id=owner.id)


def reorder(db: Session, owner: User, ids: list[str]) -> list[ActionItem]:
    """Set positions to the order of `ids` (only the owner's rows are touched; unknown ids are ignored)."""
    rows = {r.id: r for r in db.scalars(select(ActionItem).where(ActionItem.owner_id == owner.id))}
    pos = 1.0
    for iid in ids:
        if iid in rows:
            rows[iid].position = pos
            pos += 1.0
    for r in sorted((r for r in rows.values() if r.id not in set(ids)), key=lambda r: r.position):
        r.position = pos
        pos += 1.0
    db.commit()
    bus.emit("action_item.updated", entity_type="action_item", entity_id="*", actor_id=owner.id)
    return list_action_items(db, owner, include_done=True)


def counts(db: Session, owner: User) -> tuple[int, int]:
    """(open, overdue) for the owner."""
    open_ = db.scalar(
        select(func.count()).select_from(ActionItem).where(ActionItem.owner_id == owner.id, ActionItem.done.is_(False))
    ) or 0
    overdue = db.scalar(
        select(func.count()).select_from(ActionItem).where(
            ActionItem.owner_id == owner.id, ActionItem.done.is_(False), ActionItem.due_date < date.today()
        )
    ) or 0
    return int(open_), int(overdue)
