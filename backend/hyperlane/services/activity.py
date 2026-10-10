"""Activity log: one row per meaningful change (feeds the activity feed and notifications).

Other services call `record(db, ...)` inside the same transaction as the change; the caller commits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, User


def record(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    summary: str,
    project_id: str | None = None,
    actor: User | None = None,
    changes: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> Activity:
    """Add an Activity row to the session (not committed). `changes` is `{field: [old, new]}`."""
    row = Activity(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor.id if actor else None,
        actor_name=actor.name if actor else None,
        summary=summary[:400],
        changes=_jsonable(changes or {}),
    )
    if at is not None:
        row.at = at
    db.add(row)
    return row


def list_activity(
    db: Session,
    *,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
) -> list[Activity]:
    stmt = select(Activity)
    if project_id:
        stmt = stmt.where(Activity.project_id == project_id)
    if entity_type:
        stmt = stmt.where(Activity.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Activity.entity_id == entity_id)
    stmt = stmt.order_by(Activity.at.desc()).limit(limit)
    return list(db.scalars(stmt))


def _jsonable(value: Any) -> Any:
    """Make change payloads JSON-safe (dates, sets, nested dicts/lists)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
