"""Helpers shared by the integration modules: notification log, URLs, status/category lookups.

Everything here is pure / local (no network). Lazy imports of other owners' services live in
`_core()` style helpers so the package imports cleanly while those modules are still being written.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from ..config import get_settings
from ..db import session_scope
from ..models import NotificationLog, Project, User, WorkItem
from ..services.events import bus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- notification log


def record_notification(
    *,
    channel: str,
    target: str | None,
    kind: str,
    body: str,
    ok: bool,
    error: str | None = None,
    external_ref: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    """Write a `NotificationLog` row and emit `notification.sent`. Never raises."""
    try:
        with session_scope() as db:
            row = NotificationLog(
                channel=channel,
                target=target,
                kind=kind,
                entity_type=entity_type,
                entity_id=entity_id,
                body=body[:20000],
                ok=ok,
                error=(error or None) and str(error)[:2000],
                external_ref=external_ref,
                meta=meta or {},
            )
            db.add(row)
            db.flush()
            log_id = row.id
    except Exception:  # pragma: no cover - sqlite hiccup
        log.exception("could not write notification log")
        return None
    try:
        bus.emit(
            "notification.sent",
            project_id=project_id,
            entity_type="notification",
            entity_id=log_id,
            data={"channel": channel, "target": target, "kind": kind, "ok": ok, "error": error},
        )
    except Exception:  # pragma: no cover
        log.exception("notification.sent emit failed")
    return log_id


# ---------------------------------------------------------------- urls


def base_url() -> str:
    s = get_settings()
    host = s.host
    if host in ("0.0.0.0", "::", ""):
        host = "localhost"
    return f"http://{host}:{s.port}"


def item_url(item_id: str) -> str:
    return f"{base_url()}/items/{item_id}"


# ---------------------------------------------------------------- workflow helpers


def workflow_state(project: Project | None, status: str | None) -> dict[str, Any] | None:
    if project is None or not status:
        return None
    for st in project.workflow or []:
        if st.get("key") == status:
            return st
    return None


def status_name(project: Project | None, status: str | None) -> str:
    st = workflow_state(project, status)
    return st["name"] if st else (status or "").replace("_", " ").title()


def status_category(project: Project | None, status: str | None) -> str:
    st = workflow_state(project, status)
    if st:
        return st.get("category", "todo")
    if status in ("done", "live", "accepted", "resolved", "learned"):
        return "done"
    if status in ("in_progress", "review", "doing"):
        return "in_progress"
    return "todo"


def item_key(item: WorkItem) -> str:
    try:
        from ..services.items import item_key as _core_key

        return _core_key(item)
    except ImportError:
        proj = item.project
        return f"{proj.key if proj else '?'}-{item.number}"


def item_dict(item: WorkItem) -> dict[str, Any]:
    """A small, serialisable view of an item for message formatting (read-only; not the API shape)."""
    proj = item.project
    assignee = item.assignee
    return {
        "id": item.id,
        "key": item_key(item),
        "title": item.title,
        "type": item.type,
        "status": item.status,
        "status_name": status_name(proj, item.status),
        "category": status_category(proj, item.status),
        "priority": item.priority,
        "points": item.points,
        "assignee_id": item.assignee_id,
        "assignee_name": assignee.name if assignee else None,
        "project_id": item.project_id,
        "project_key": proj.key if proj else None,
        "project_name": proj.name if proj else None,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "blocked": bool(item.blocked),
        "blocked_reason": item.blocked_reason,
        "url": item_url(item.id),
    }


def user_name(db, user_id: str | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    return u.name if u else None


# ---------------------------------------------------------------- time helpers


def local_today() -> date:
    return datetime.now().astimezone().date()


def to_local_date(dt: datetime | None) -> date | None:
    """Naive-UTC datetime (as stored) -> local calendar date."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().date()


def pref(user: User | None, key: str, default: bool = False) -> bool:
    if user is None:
        return default
    prefs = user.preferences or {}
    val = prefs.get(key, default)
    return bool(val)
