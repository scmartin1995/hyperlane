"""Glue to the services written by the other slices (backend-core, backend-analytics, integrations).

Those modules are being written in parallel; everything here imports them lazily, adapts to
their call signatures by parameter *name*, and degrades to a clear "not available yet" error
instead of crashing the agent. Read-only lookups fall back to plain ORM queries. The only
write that has a fallback is `bulk_create` (a deliberately minimal stopgap so the importer,
backlog builder and intake conversion still work before `services.items` lands).
"""

from __future__ import annotations

import importlib
import inspect
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Label, Project, Sprint, User, WorkItem
from ..services.events import bus
from ..services.templates import first_status

log = logging.getLogger(__name__)


class NotAvailable(RuntimeError):
    """A sibling service isn't written yet (or exposes a different name)."""


def service(module: str, name: str):
    """Return `hyperlane.services.<module>.<name>` or raise NotAvailable."""
    try:
        mod = importlib.import_module(f"hyperlane.services.{module}")
    except ImportError as exc:
        raise NotAvailable(f"services.{module} is not available yet ({exc.__class__.__name__})") from exc
    fn = getattr(mod, name, None)
    if fn is None:
        raise NotAvailable(f"services.{module}.{name} is not available yet")
    return fn


def integration(module: str, name: str):
    try:
        mod = importlib.import_module(f"hyperlane.integrations.{module}")
    except ImportError as exc:
        raise NotAvailable(f"integrations.{module} is not available ({exc.__class__.__name__})") from exc
    fn = getattr(mod, name, None)
    if fn is None:
        raise NotAvailable(f"integrations.{module}.{name} is not available")
    return fn


def call_adaptive(fn, /, **candidates: Any):
    """Call `fn` passing only the keyword arguments it declares (bound by name).

    Lets us call a sibling service whose exact signature we can't see yet, e.g.
    `bulk_create(db, project, items, user)` vs `bulk_create(db, project_id, items, actor)`.
    Positional-only parameters are filled in declaration order from the same candidates.
    """
    sig = inspect.signature(fn)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        if p.name in candidates:
            if p.kind is inspect.Parameter.POSITIONAL_ONLY:
                args.append(candidates[p.name])
            else:
                kwargs[p.name] = candidates[p.name]
        elif p.default is inspect.Parameter.empty and p.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise NotAvailable(f"{fn.__module__}.{fn.__name__} needs an argument we don't know: {p.name!r}")
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Read helpers (safe to do directly against the ORM)
# ---------------------------------------------------------------------------


def item_key(item: WorkItem, project: Project | None = None) -> str:
    try:
        fn = service("items", "item_key")
        return call_adaptive(fn, item=item, project=project or item.project)
    except NotAvailable:
        proj = project or item.project
        return f"{proj.key}-{item.number}"


def serialize_item(db: Session, item: WorkItem, *, compact: bool = True) -> dict[str, Any]:
    """Compact dict for tool results (agent context is precious)."""
    try:
        fn = service("items", "serialize_item")
        data = call_adaptive(fn, db=db, item=item)
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        if compact and isinstance(data, dict):
            return _compact(data)
        return data
    except NotAvailable:
        pass
    d = {
        "id": item.id,
        "key": item_key(item),
        "type": item.type,
        "title": item.title,
        "status": item.status,
        "priority": item.priority,
        "points": item.points,
        "parent_id": item.parent_id,
        "sprint_id": item.sprint_id,
        "assignee": item.assignee.name if item.assignee else None,
        "labels": [lb.name for lb in item.labels],
        "blocked": item.blocked,
        "due_date": item.due_date.isoformat() if item.due_date else None,
    }
    if not compact:
        d.update(
            {
                "description": item.description,
                "acceptance_criteria": item.acceptance_criteria,
                "business_value": item.business_value,
                "estimate_hours": item.estimate_hours,
                "blocked_reason": item.blocked_reason,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
        )
    return d


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id",
        "key",
        "type",
        "title",
        "status",
        "priority",
        "points",
        "parent_id",
        "sprint_id",
        "blocked",
        "due_date",
    )
    out = {k: data.get(k) for k in keep if k in data}
    assignee = data.get("assignee")
    out["assignee"] = assignee.get("name") if isinstance(assignee, dict) else None
    out["labels"] = [lb.get("name") if isinstance(lb, dict) else lb for lb in data.get("labels") or []]
    return out


def resolve_item(db: Session, id_or_key: str) -> WorkItem | None:
    """Find an item by id or display key (`HL-12`, case-insensitive)."""
    if not id_or_key:
        return None
    item = db.get(WorkItem, id_or_key)
    if item is not None:
        return item
    if "-" in id_or_key:
        key, _, num = id_or_key.rpartition("-")
        if num.isdigit():
            proj = db.scalar(select(Project).where(func.upper(Project.key) == key.upper()))
            if proj is not None:
                return db.scalar(
                    select(WorkItem).where(WorkItem.project_id == proj.id, WorkItem.number == int(num))
                )
    return None


def resolve_project(db: Session, ref: str | None) -> Project | None:
    if not ref:
        return None
    proj = db.get(Project, ref)
    if proj is not None:
        return proj
    return db.scalar(select(Project).where(func.upper(Project.key) == ref.upper())) or db.scalar(
        select(Project).where(func.lower(Project.name) == ref.lower())
    )


def resolve_user(db: Session, ref: str | None) -> User | None:
    if not ref:
        return None
    u = db.get(User, ref)
    if u is not None:
        return u
    ref_l = ref.lower().lstrip("@")
    return db.scalar(
        select(User).where(
            (func.lower(User.handle) == ref_l) | (func.lower(User.name) == ref_l) | (func.lower(User.email) == ref_l)
        )
    )


def type_for_level(project: Project, level: int) -> str | None:
    for t in sorted(project.item_types or [], key=lambda t: t.get("level", 0)):
        if t.get("level", 0) == level:
            return t["key"]
    return None


def type_level(project: Project, type_key: str) -> int | None:
    for t in project.item_types or []:
        if t["key"] == type_key:
            return int(t.get("level", 0))
    return None


def leaf_type(project: Project) -> str:
    settings = project.settings or {}
    if settings.get("default_type"):
        return settings["default_type"]
    types = project.item_types or []
    if not types:
        return "story"
    return max(types, key=lambda t: t.get("level", 0))["key"]


# ---------------------------------------------------------------------------
# Writes: prefer services.items, fall back to a minimal stopgap
# ---------------------------------------------------------------------------


def bulk_create(db: Session, project: Project, items: list[dict[str, Any]], user: User | None) -> list[WorkItem]:
    """Create items (supports temp_id / parent_temp_id hierarchies) through services.items.bulk_create."""
    try:
        fn = service("items", "bulk_create")
    except NotAvailable:
        log.warning("services.items.bulk_create not available yet; using the agent's minimal fallback")
        return _bulk_create_fallback(db, project, items, user)
    created = call_adaptive(
        fn,
        db=db,
        project=project,
        project_id=project.id,
        items=items,
        payload=items,
        data=items,
        user=user,
        actor=user,
        actor_id=user.id if user else None,
        reporter=user,
        current_user=user,
    )
    return list(created)


def _bulk_create_fallback(
    db: Session, project: Project, items: list[dict[str, Any]], user: User | None
) -> list[WorkItem]:
    workflow = project.workflow or []
    default_status = first_status(workflow)
    valid_status = {s["key"] for s in workflow}
    valid_types = {t["key"] for t in (project.item_types or [])}
    default_type = leaf_type(project)
    max_rank = db.scalar(select(func.max(WorkItem.rank)).where(WorkItem.project_id == project.id)) or 0.0
    by_temp: dict[str, WorkItem] = {}
    created: list[WorkItem] = []
    number = project.next_item_number or 1
    for i, spec in enumerate(items):
        spec = dict(spec)
        status = spec.get("status") or default_status
        if status not in valid_status:
            status = default_status
        itype = spec.get("type") or default_type
        if valid_types and itype not in valid_types:
            itype = default_type
        due = spec.get("due_date")
        if isinstance(due, str):
            try:
                due = date.fromisoformat(due[:10])
            except ValueError:
                due = None
        item = WorkItem(
            project_id=project.id,
            number=number,
            type=itype,
            title=str(spec.get("title") or "Untitled")[:300],
            description=spec.get("description"),
            acceptance_criteria=spec.get("acceptance_criteria"),
            status=status,
            priority=spec.get("priority") or "medium",
            points=spec.get("points"),
            estimate_hours=spec.get("estimate_hours"),
            business_value=spec.get("business_value"),
            rank=max_rank + 1000.0 * (i + 1),
            assignee_id=spec.get("assignee_id"),
            reporter_id=user.id if user else None,
            sprint_id=spec.get("sprint_id"),
            due_date=due,
            source=spec.get("source") or "agent",
            source_ref=spec.get("source_ref"),
            custom=spec.get("custom") or {},
        )
        number += 1
        parent_temp = spec.get("parent_temp_id")
        if parent_temp and parent_temp in by_temp:
            item.parent = by_temp[parent_temp]
        elif spec.get("parent_id"):
            item.parent_id = spec["parent_id"]
        for name in spec.get("labels") or []:
            name = str(name).strip()
            if not name:
                continue
            label = db.scalar(select(Label).where(Label.project_id == project.id, Label.name == name))
            if label is None:
                label = Label(project_id=project.id, name=name)
                db.add(label)
                db.flush()
            item.labels.append(label)
        db.add(item)
        if spec.get("temp_id"):
            by_temp[str(spec["temp_id"])] = item
        created.append(item)
    project.next_item_number = number
    db.flush()
    for item in created:
        bus.emit(
            "work_item.created",
            project_id=project.id,
            entity_type="work_item",
            entity_id=item.id,
            actor_id=user.id if user else None,
            data={"key": f"{project.key}-{item.number}", "title": item.title, "source": item.source},
        )
    return created


def active_sprint(db: Session, project_id: str) -> Sprint | None:
    return db.scalar(select(Sprint).where(Sprint.project_id == project_id, Sprint.state == "active"))


def today() -> date:
    return datetime.now(UTC).date()


def item_out(db: Session, item: WorkItem) -> dict[str, Any]:
    """Full `WorkItem` API shape for router responses (prefers the core serializer)."""
    try:
        fn = service("items", "serialize_item")
        data = call_adaptive(fn, db=db, item=item)
        return data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    except NotAvailable:
        from ..schemas.common import WorkItemOut

        out = WorkItemOut.model_validate(item)
        out.key = item_key(item)
        out.comment_count = len(item.comments)
        out.child_count = len([ch for ch in item.children if not ch.is_archived])
        return out.model_dump(mode="json")
