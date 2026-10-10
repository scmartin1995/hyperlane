"""Work items: CRUD, hierarchy, fractional ranking, status transitions, comments, search.

Public signatures here are a contract: the agent tools, integrations and analytics import them.
Every mutating function commits and then emits an event on `services.events.bus`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import utcnow
from ..models import Comment, Label, Project, Sprint, SprintCommitment, StatusTransition, User, WorkItem
from ..schemas.common import CommentOut, LabelOut, SprintOut, UserBrief, WorkItemOut
from . import ranking
from .activity import _jsonable, record
from .events import bus
from .templates import first_status, status_category

PRIORITIES = ("critical", "high", "medium", "low", "none")
SOURCES = ("manual", "agent", "email", "excel", "slack", "import", "chat", "teams")
UNSET = ranking.UNSET  # sentinel: "argument not given" (distinct from None = clear)

_SIMPLE_FIELDS = (
    "title", "description", "acceptance_criteria", "priority", "points", "estimate_hours", "actual_hours",
    "actual_cost", "business_value", "due_date", "blocked", "blocked_reason", "custom", "source", "source_ref",
)  # fmt: skip


# ---------- helpers ----------


def item_key(item: WorkItem) -> str:
    return f"{item.project.key}-{item.number}"


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _workflow_keys(project: Project) -> list[str]:
    return [s["key"] for s in project.workflow]


def _done_keys(project: Project) -> set[str]:
    return {s["key"] for s in project.workflow if s["category"] == "done"}


def _type_keys(project: Project) -> set[str]:
    return {t["key"] for t in project.item_types}


def _get_item(db: Session, item_id: str | None, project: Project, what: str) -> WorkItem:
    it = db.get(WorkItem, item_id) if item_id else None
    if it is None or it.project_id != project.id:
        raise ValueError(f"{what} not found in this project")
    return it


def _check_parent(db: Session, item: WorkItem | None, parent_id: str | None, project: Project) -> None:
    if parent_id is None:
        return
    parent = _get_item(db, parent_id, project, "parent")
    if item is not None:
        if parent.id == item.id:
            raise ValueError("an item cannot be its own parent")
        # cycle check: walk up from the parent
        seen = {item.id}
        cur: WorkItem | None = parent
        while cur is not None:
            if cur.id in seen:
                raise ValueError("that move would create a cycle in the hierarchy")
            seen.add(cur.id)
            cur = cur.parent


def _check_sprint(db: Session, sprint_id: str | None, project: Project) -> Sprint | None:
    if sprint_id is None:
        return None
    sprint = db.get(Sprint, sprint_id)
    if sprint is None or sprint.project_id != project.id:
        raise ValueError("sprint not found in this project")
    return sprint


def _check_user(db: Session, user_id: str | None) -> None:
    if user_id is not None and db.get(User, user_id) is None:
        raise ValueError("assignee not found")


def resolve_labels(db: Session, project: Project, names: list[str]) -> list[Label]:
    """Label names → Label rows (created on the fly, case-insensitive match)."""
    existing = {lab.name.lower(): lab for lab in db.scalars(select(Label).where(Label.project_id == project.id))}
    out: list[Label] = []
    for raw in names:
        name = (raw or "").strip()[:60]
        if not name:
            continue
        lab = existing.get(name.lower())
        if lab is None:
            lab = Label(project_id=project.id, name=name)
            db.add(lab)
            db.flush()
            existing[name.lower()] = lab
        if lab not in out:
            out.append(lab)
    return out


def wip_warning(db: Session, project: Project, status: str) -> str | None:
    """Text when `status` holds more live items than its `wip_limit`, else None."""
    state = next((s for s in project.workflow if s["key"] == status), None)
    if not state or not state.get("wip_limit"):
        return None
    db.flush()  # the session has autoflush off; count what was just changed
    count = db.scalar(
        select(func.count()).select_from(WorkItem).where(
            WorkItem.project_id == project.id, WorkItem.status == status, WorkItem.is_archived.is_(False)
        )
    ) or 0
    if count > state["wip_limit"]:
        return f"{state['name']} is over its WIP limit ({count}/{state['wip_limit']})"
    return None


# ---------- serialization ----------


def _counts(db: Session, ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    comments = {
        k: int(v) for k, v in db.execute(
            select(Comment.work_item_id, func.count()).where(Comment.work_item_id.in_(ids)).group_by(Comment.work_item_id)
        )
    }  # fmt: skip
    children = {
        k: int(v) for k, v in db.execute(
            select(WorkItem.parent_id, func.count())
            .where(WorkItem.parent_id.in_(ids), WorkItem.is_archived.is_(False))
            .group_by(WorkItem.parent_id)
        )
    }  # fmt: skip
    return comments, children


def serialize_items(items: list[WorkItem], db: Session) -> list[WorkItemOut]:
    """Batch version of `serialize_item` (two grouped count queries instead of 2N)."""
    if not items:
        return []
    db.flush()
    comments, children = _counts(db, [i.id for i in items])
    out: list[WorkItemOut] = []
    for it in items:
        o = WorkItemOut.model_validate(it)
        o.key = item_key(it)
        o.comment_count = comments.get(it.id, 0)
        o.child_count = children.get(it.id, 0)
        o.labels = [LabelOut.model_validate(lab) for lab in sorted(it.labels, key=lambda x: x.name.lower())]
        o.assignee = UserBrief.model_validate(it.assignee) if it.assignee else None
        out.append(o)
    return out


def serialize_item(item: WorkItem, db: Session) -> WorkItemOut:
    """`WorkItem` shape from types.ts: key, comment_count, child_count, labels, assignee filled."""
    return serialize_items([item], db)[0]


def serialize_comment(comment: Comment) -> CommentOut:
    out = CommentOut.model_validate(comment)
    out.author = UserBrief.model_validate(comment.author) if comment.author else None
    return out


def list_children(db: Session, item: WorkItem, *, include_archived: bool = False) -> list[WorkItem]:
    stmt = select(WorkItem).where(WorkItem.parent_id == item.id).order_by(WorkItem.rank, WorkItem.number)
    if not include_archived:
        stmt = stmt.where(WorkItem.is_archived.is_(False))
    return list(db.scalars(stmt.options(selectinload(WorkItem.labels), selectinload(WorkItem.assignee))))


def serialize_detail(item: WorkItem, db: Session) -> dict[str, Any]:
    """`WorkItemDetail`: WorkItem + children, comments (with author), parent, sprint. JSON-ready dict."""
    base = serialize_item(item, db).model_dump(mode="json")
    base["children"] = [o.model_dump(mode="json") for o in serialize_items(list_children(db, item), db)]
    comments = sorted(item.comments, key=lambda c: c.created_at)
    base["comments"] = [serialize_comment(c).model_dump(mode="json") for c in comments]
    base["parent"] = serialize_item(item.parent, db).model_dump(mode="json") if item.parent else None
    base["sprint"] = SprintOut.model_validate(item.sprint).model_dump(mode="json") if item.sprint else None
    return base


# ---------- queries ----------


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def list_items(
    db: Session,
    project_id: str,
    *,
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
) -> list[WorkItem]:
    """Items of a project ordered by rank. `sprint_id="none"`/`unscheduled` = no sprint; comma lists allowed
    for type/status; `assignee_id`/`parent_id` accept "none" too."""
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("project not found")
    stmt = (
        select(WorkItem)
        .where(WorkItem.project_id == project_id)
        .options(selectinload(WorkItem.labels), selectinload(WorkItem.assignee))
    )
    if not include_archived:
        stmt = stmt.where(WorkItem.is_archived.is_(False))
    if types := _split(type):
        stmt = stmt.where(WorkItem.type.in_(types))
    if statuses := _split(status):
        stmt = stmt.where(WorkItem.status.in_(statuses))
    if category:
        keys = [s["key"] for s in project.workflow if s["category"] in _split(category)]
        stmt = stmt.where(WorkItem.status.in_(keys))
    if unscheduled or sprint_id == "none":
        stmt = stmt.where(WorkItem.sprint_id.is_(None))
    elif sprint_id:
        stmt = stmt.where(WorkItem.sprint_id == sprint_id)
    if assignee_id == "none":
        stmt = stmt.where(WorkItem.assignee_id.is_(None))
    elif assignee_id:
        stmt = stmt.where(WorkItem.assignee_id == assignee_id)
    if parent_id == "none":
        stmt = stmt.where(WorkItem.parent_id.is_(None))
    elif parent_id:
        stmt = stmt.where(WorkItem.parent_id == parent_id)
    if q:
        stmt = stmt.where(_text_filter(project, q))
    if label:
        stmt = stmt.where(WorkItem.labels.any(func.lower(Label.name) == label.lower()))
    if not include_done and (done := _done_keys(project)):
        stmt = stmt.where(WorkItem.status.not_in(done))
    stmt = stmt.order_by(WorkItem.rank, WorkItem.number)
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def _text_filter(project: Project | None, q: str):
    q = q.strip()
    like = f"%{q}%"
    clauses = [WorkItem.title.ilike(like), WorkItem.description.ilike(like)]
    m = re.fullmatch(r"(?:([A-Za-z][A-Za-z0-9]*)-)?(\d+)", q)
    if m and (project is None or m.group(1) is None or m.group(1).upper() == project.key):
        clauses.append(WorkItem.number == int(m.group(2)))
    return or_(*clauses)


def item_tree(db: Session, project_id: str, include_done: bool = True) -> list[dict[str, Any]]:
    """`WorkItemTreeNode[]`: roots (no parent) nested by parent_id, each level ordered by rank.
    With include_done=False, done items are pruned unless they still have live descendants."""
    items = list_items(db, project_id, include_done=True)
    outs = serialize_items(items, db)
    nodes: dict[str, dict[str, Any]] = {o.id: {**o.model_dump(mode="json"), "children": []} for o in outs}
    roots: list[dict[str, Any]] = []
    for o in outs:
        node = nodes[o.id]
        if o.parent_id and o.parent_id in nodes:
            nodes[o.parent_id]["children"].append(node)
        else:
            roots.append(node)
    if include_done:
        return roots
    project = db.get(Project, project_id)
    done = _done_keys(project) if project else set()

    def prune(level: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept = []
        for n in level:
            n["children"] = prune(n["children"])
            if n["status"] not in done or n["children"]:
                kept.append(n)
        return kept

    return prune(roots)


# ---------- status ----------


def apply_status(
    db: Session, item: WorkItem, new_status: str, actor: User | None, *, at: datetime | None = None
) -> bool:
    """Change status: writes a StatusTransition, maintains started_at/completed_at. Returns True if changed.
    Does not commit."""
    project = item.project
    if new_status not in _workflow_keys(project):
        raise ValueError(f"'{new_status}' is not a state of this project's workflow")
    if new_status == item.status:
        return False
    at = at or utcnow()
    old, old_cat, new_cat = item.status, status_category(project.workflow, item.status), status_category(project.workflow, new_status)
    db.add(
        StatusTransition(
            work_item_id=item.id, project_id=item.project_id, from_status=old, to_status=new_status,
            from_category=old_cat, to_category=new_cat, actor_id=actor.id if actor else None, at=at,
        )
    )  # fmt: skip
    item.status = new_status
    if new_cat == "in_progress" and item.started_at is None:
        item.started_at = at
    if new_cat == "done":
        item.completed_at = at
    elif old_cat == "done":
        item.completed_at = None
    return True


def _track_sprint_scope(db: Session, item: WorkItem, old_sprint_id: str | None, new_sprint_id: str | None) -> None:
    """Keep SprintCommitment rows honest when scope changes mid-sprint."""
    now = utcnow()
    if old_sprint_id:
        old = db.get(Sprint, old_sprint_id)
        if old and old.state == "active":
            for c in db.scalars(
                select(SprintCommitment).where(
                    SprintCommitment.sprint_id == old.id, SprintCommitment.work_item_id == item.id,
                    SprintCommitment.removed_at.is_(None),
                )
            ):  # fmt: skip
                c.removed_at = now
    if new_sprint_id:
        new = db.get(Sprint, new_sprint_id)
        if new and new.state == "active":
            db.add(
                SprintCommitment(
                    sprint_id=new.id, work_item_id=item.id, points=item.points, added_at=now, added_mid_sprint=True
                )
            )


# ---------- create ----------


def _build_item(db: Session, project: Project, data: dict[str, Any], actor: User | None) -> WorkItem:
    """Construct + flush a WorkItem (no commit, no activity, no event)."""
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    type_ = data.get("type") or project.settings.get("default_type") or project.item_types[-1]["key"]
    if type_ not in _type_keys(project):
        raise ValueError(f"'{type_}' is not an item type of this project")
    status = data.get("status") or first_status(project.workflow, "todo")
    if status not in _workflow_keys(project):
        raise ValueError(f"'{status}' is not a state of this project's workflow")
    priority = data.get("priority") or "medium"
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
    parent_id = data.get("parent_id") or None
    _check_parent(db, None, parent_id, project)
    sprint_id = data.get("sprint_id") or None
    _check_sprint(db, sprint_id, project)
    assignee_id = data.get("assignee_id") or None
    _check_user(db, assignee_id)

    item = WorkItem(
        project_id=project.id,
        number=project.next_item_number,
        type=type_,
        parent_id=parent_id,
        title=title[:300],
        description=data.get("description"),
        acceptance_criteria=data.get("acceptance_criteria"),
        status=status,
        priority=priority,
        points=data.get("points"),
        estimate_hours=data.get("estimate_hours"),
        actual_hours=data.get("actual_hours"),
        actual_cost=data.get("actual_cost"),
        business_value=data.get("business_value"),
        rank=ranking.last_rank(db, project.id),
        assignee_id=assignee_id,
        reporter_id=data.get("reporter_id") or (actor.id if actor else None),
        sprint_id=sprint_id,
        due_date=_to_date(data.get("due_date")),
        source=data.get("source") or "manual",
        source_ref=data.get("source_ref"),
        blocked=bool(data.get("blocked") or False),
        blocked_reason=data.get("blocked_reason"),
        custom=dict(data.get("custom") or {}),
    )
    project.next_item_number += 1
    db.add(item)
    db.flush()
    if data.get("labels"):
        item.labels = resolve_labels(db, project, list(data["labels"]))
    cat = status_category(project.workflow, status)
    now = utcnow()
    if cat == "in_progress":
        item.started_at = now
    elif cat == "done":
        item.completed_at = now
    db.add(
        StatusTransition(
            work_item_id=item.id, project_id=project.id, from_status=None, to_status=status,
            from_category=None, to_category=cat, actor_id=actor.id if actor else None, at=now,
        )
    )  # fmt: skip
    if sprint_id:
        _track_sprint_scope(db, item, None, sprint_id)
    db.flush()
    return item


def create_item(db: Session, project: Project, data: dict[str, Any], actor: User | None) -> WorkItem:
    """Create one item. Defaults: type=settings.default_type, status=first todo state, rank=last.
    `labels` are names (created if missing). Writes Activity and emits `work_item.created`."""
    item = _build_item(db, project, data, actor)
    record(
        db, entity_type="work_item", entity_id=item.id, action="created", project_id=project.id, actor=actor,
        summary=f"Created {item.type} {item_key(item)}: {item.title}",
    )
    db.commit()
    bus.emit(
        "work_item.created", project_id=project.id, entity_type="work_item", entity_id=item.id,
        actor_id=actor.id if actor else None, data={"key": item_key(item), "type": item.type},
    )  # fmt: skip
    return item


def bulk_create(db: Session, project: Project, items: list[dict[str, Any]], actor: User | None) -> list[WorkItem]:
    """Create many items in one transaction. Each dict may carry `temp_id` and `parent_temp_id` to build a
    hierarchy in one call (order independent); `parent_id` may be a real id or a temp id."""
    pending = [dict(d) for d in items]
    temp: dict[str, WorkItem] = {}
    created: list[WorkItem] = []
    while pending:
        progressed = False
        remaining: list[dict[str, Any]] = []
        for d in pending:
            ref = d.get("parent_temp_id") or d.get("parent_id")
            if ref and ref in temp:
                d["parent_id"] = temp[ref].id
            elif ref and d.get("parent_temp_id") and db.get(WorkItem, ref) is None:
                remaining.append(d)  # parent not created yet
                continue
            temp_id = d.pop("temp_id", None)
            d.pop("parent_temp_id", None)
            item = _build_item(db, project, d, actor)
            if temp_id:
                temp[str(temp_id)] = item
            created.append(item)
            progressed = True
        if not progressed:
            missing = sorted({str(d.get("parent_temp_id")) for d in remaining})
            raise ValueError(f"bulk create: unknown parent_temp_id(s): {', '.join(missing)}")
        pending = remaining
    for item in created:
        record(
            db, entity_type="work_item", entity_id=item.id, action="created", project_id=project.id, actor=actor,
            summary=f"Created {item.type} {item_key(item)}: {item.title}",
        )
    db.commit()
    for item in created:
        bus.emit(
            "work_item.created", project_id=project.id, entity_type="work_item", entity_id=item.id,
            actor_id=actor.id if actor else None, data={"key": item_key(item), "type": item.type, "bulk": True},
        )  # fmt: skip
    return created


# ---------- update / move / archive ----------


def _diff(changes: dict[str, list[Any]], field: str, old: Any, new: Any) -> bool:
    if old == new:
        return False
    changes[field] = [old, new]
    return True


def update_item(db: Session, item: WorkItem, data: dict[str, Any], actor: User | None) -> WorkItem:
    """Partial update. Status changes go through `apply_status`; label names are resolved/created.
    Writes Activity with `changes {field: [old, new]}` and emits `work_item.updated` with `data.changes`."""
    project = item.project
    changes: dict[str, list[Any]] = {}

    for field in _SIMPLE_FIELDS:
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
        elif field == "due_date":
            value = _to_date(value)
        elif field == "blocked":
            value = bool(value)
        elif field == "custom":
            value = {**(item.custom or {}), **(value or {})}
        elif field == "source":
            value = value or "manual"
        if _diff(changes, field, getattr(item, field), value):
            setattr(item, field, value)

    if "type" in data and data["type"] and data["type"] != item.type:
        if data["type"] not in _type_keys(project):
            raise ValueError(f"'{data['type']}' is not an item type of this project")
        changes["type"] = [item.type, data["type"]]
        item.type = data["type"]

    if "parent_id" in data and (data["parent_id"] or None) != item.parent_id:
        _check_parent(db, item, data["parent_id"] or None, project)
        changes["parent_id"] = [item.parent_id, data["parent_id"] or None]
        item.parent_id = data["parent_id"] or None

    if "sprint_id" in data and (data["sprint_id"] or None) != item.sprint_id:
        new_sprint = data["sprint_id"] or None
        _check_sprint(db, new_sprint, project)
        changes["sprint_id"] = [item.sprint_id, new_sprint]
        _track_sprint_scope(db, item, item.sprint_id, new_sprint)
        item.sprint_id = new_sprint

    if "assignee_id" in data and (data["assignee_id"] or None) != item.assignee_id:
        _check_user(db, data["assignee_id"] or None)
        changes["assignee_id"] = [item.assignee_id, data["assignee_id"] or None]
        item.assignee_id = data["assignee_id"] or None

    if "labels" in data and data["labels"] is not None:
        new_labels = resolve_labels(db, project, list(data["labels"]))
        old_names = sorted(lab.name for lab in item.labels)
        new_names = sorted(lab.name for lab in new_labels)
        if old_names != new_names:
            changes["labels"] = [old_names, new_names]
            item.labels = new_labels

    if "status" in data and data["status"] and data["status"] != item.status:
        old = item.status
        apply_status(db, item, data["status"], actor)
        changes["status"] = [old, item.status]

    if "rank" in data and data["rank"] is not None and _diff(changes, "rank", item.rank, float(data["rank"])):
        item.rank = float(data["rank"])

    if changes:
        item.updated_at = utcnow()
        record(
            db, entity_type="work_item", entity_id=item.id, action="updated", project_id=project.id, actor=actor,
            summary=_summary(item, changes), changes=changes,
        )
    db.commit()
    bus.emit(
        "work_item.updated", project_id=project.id, entity_type="work_item", entity_id=item.id,
        actor_id=actor.id if actor else None, data={"changes": _jsonable(changes), "key": item_key(item)},
    )  # fmt: skip
    return item


def _summary(item: WorkItem, changes: dict[str, list[Any]]) -> str:
    key = item_key(item)
    if "status" in changes:
        return f"{key} moved from {changes['status'][0]} to {changes['status'][1]}"
    if list(changes) == ["assignee_id"]:
        who = item.assignee.name if item.assignee else "nobody"
        return f"{key} assigned to {who}"
    return f"{key} updated ({', '.join(changes)})"


def bulk_update(db: Session, items: list[WorkItem], patch: dict[str, Any], actor: User | None) -> list[WorkItem]:
    return [update_item(db, it, dict(patch), actor) for it in items]


def _rank_for_position(db: Session, item: WorkItem, before_id: str | None, after_id: str | None) -> float:
    """`after_id` = the item the moved one lands *after* (above it); `before_id` = the one it lands *before*."""
    project = item.project
    above = _get_item(db, after_id, project, "after_id item") if after_id else None
    below = _get_item(db, before_id, project, "before_id item") if before_id else None
    if (above and above.id == item.id) or (below and below.id == item.id):
        raise ValueError("an item cannot be positioned relative to itself")
    for _attempt in range(2):
        if above is not None and below is None:
            _, nxt = ranking.neighbours(db, above, exclude_id=item.id)
            lo, hi = above.rank, (nxt.rank if nxt else None)
        elif below is not None and above is None:
            prev, _ = ranking.neighbours(db, below, exclude_id=item.id)
            lo, hi = (prev.rank if prev else None), below.rank
        else:
            lo, hi = sorted((above.rank, below.rank))  # type: ignore[union-attr]
        if ranking.needs_renormalize(lo, hi):
            ranking.renormalize(db, project.id)
            continue
        return ranking.rank_between(lo, hi)
    return ranking.rank_between(lo, hi)  # pragma: no cover


def move_item(
    db: Session,
    item: WorkItem,
    *,
    status: str | None = None,
    sprint_id: Any = UNSET,
    parent_id: Any = UNSET,
    before_id: str | None = None,
    after_id: str | None = None,
    actor: User | None = None,
) -> tuple[WorkItem, str | None]:
    """Board / sprint / hierarchy drag + reorder. `sprint_id`/`parent_id` default to "unchanged"; pass None to
    clear. Returns (item, wip_warning) and emits `work_item.moved`."""
    project = item.project
    changes: dict[str, list[Any]] = {}
    if status is not None and status != item.status:
        old = item.status
        apply_status(db, item, status, actor)
        changes["status"] = [old, status]
    if sprint_id is not UNSET and (sprint_id or None) != item.sprint_id:
        new_sprint = sprint_id or None
        _check_sprint(db, new_sprint, project)
        changes["sprint_id"] = [item.sprint_id, new_sprint]
        _track_sprint_scope(db, item, item.sprint_id, new_sprint)
        item.sprint_id = new_sprint
    if parent_id is not UNSET and (parent_id or None) != item.parent_id:
        _check_parent(db, item, parent_id or None, project)
        changes["parent_id"] = [item.parent_id, parent_id or None]
        item.parent_id = parent_id or None
    if before_id or after_id:
        new_rank = _rank_for_position(db, item, before_id, after_id)
        if new_rank != item.rank:
            changes["rank"] = [item.rank, new_rank]
            item.rank = new_rank
    warning = wip_warning(db, project, item.status) if status is not None else None
    if changes:
        item.updated_at = utcnow()
        record(
            db, entity_type="work_item", entity_id=item.id, action="moved", project_id=project.id, actor=actor,
            summary=_summary(item, changes) if "status" in changes else f"{item_key(item)} moved ({', '.join(changes)})",
            changes=changes,
        )
    db.commit()
    bus.emit(
        "work_item.moved", project_id=project.id, entity_type="work_item", entity_id=item.id,
        actor_id=actor.id if actor else None,
        data={"changes": _jsonable(changes), "wip_warning": warning, "key": item_key(item)},
    )  # fmt: skip
    return item, warning


def archive_item(db: Session, item: WorkItem, actor: User | None, hard: bool = False) -> None:
    """Soft-archive (default, cascades to descendants) or hard-delete the item. Emits `work_item.deleted`."""
    project_id, item_id, key = item.project_id, item.id, item_key(item)
    if hard:
        db.delete(item)
    else:
        stack = [item]
        while stack:
            cur = stack.pop()
            cur.is_archived = True
            cur.updated_at = utcnow()
            stack.extend(c for c in cur.children if not c.is_archived)
    record(
        db, entity_type="work_item", entity_id=item_id, action="deleted" if hard else "archived",
        project_id=project_id, actor=actor, summary=f"{key} {'deleted' if hard else 'archived'}",
    )  # fmt: skip
    db.commit()
    bus.emit(
        "work_item.deleted", project_id=project_id, entity_type="work_item", entity_id=item_id,
        actor_id=actor.id if actor else None, data={"hard": hard, "key": key},
    )  # fmt: skip


# ---------- comments ----------


def add_comment(
    db: Session,
    item: WorkItem,
    body: str,
    *,
    author: User | None = None,
    author_name: str | None = None,
    source: str = "web",
    external_ref: str | None = None,
    is_decision: bool = False,
) -> Comment:
    body = (body or "").strip()
    if not body:
        raise ValueError("comment body is required")
    comment = Comment(
        work_item_id=item.id,
        author_id=author.id if author else None,
        author_name=author_name or (author.name if author else None),
        body=body,
        source=source,
        external_ref=external_ref,
        is_decision=is_decision,
    )
    db.add(comment)
    db.flush()
    record(
        db, entity_type="work_item", entity_id=item.id, action="commented", project_id=item.project_id, actor=author,
        summary=f"{comment.author_name or 'Someone'} commented on {item_key(item)}"
        + (" (decision)" if is_decision else ""),
        changes={"comment_id": [None, comment.id]},
    )
    db.commit()
    bus.emit(
        "comment.created", project_id=item.project_id, entity_type="comment", entity_id=comment.id,
        actor_id=author.id if author else None,
        data={"work_item_id": item.id, "key": item_key(item), "is_decision": is_decision, "source": source},
    )  # fmt: skip
    return comment


def update_comment(db: Session, comment: Comment, data: dict[str, Any], actor: User | None) -> Comment:
    if data.get("body") is not None:
        body = data["body"].strip()
        if not body:
            raise ValueError("comment body cannot be empty")
        if body != comment.body:
            comment.body = body
            comment.edited_at = utcnow()
    if data.get("is_decision") is not None:
        comment.is_decision = bool(data["is_decision"])
    db.commit()
    item = comment.item
    bus.emit(
        "comment.updated", project_id=item.project_id, entity_type="comment", entity_id=comment.id,
        actor_id=actor.id if actor else None, data={"work_item_id": item.id},
    )  # fmt: skip
    return comment


def delete_comment(db: Session, comment: Comment, actor: User | None) -> None:
    item = comment.item
    pid, iid, cid = item.project_id, item.id, comment.id
    db.delete(comment)
    db.commit()
    bus.emit(
        "comment.deleted", project_id=pid, entity_type="comment", entity_id=cid,
        actor_id=actor.id if actor else None, data={"work_item_id": iid},
    )  # fmt: skip


# ---------- search / personal ----------


def search_items(db: Session, q: str, limit: int = 20) -> list[WorkItem]:
    """Across projects: exact key (`HL-12`) first, then title/description contains."""
    q = (q or "").strip()
    if not q:
        return []
    results: list[WorkItem] = []
    seen: set[str] = set()
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)-(\d+)", q)
    if m:
        project = db.scalar(select(Project).where(Project.key == m.group(1).upper()))
        if project:
            hit = db.scalar(
                select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.number == int(m.group(2)))
            )
            if hit:
                results.append(hit)
                seen.add(hit.id)
    stmt = (
        select(WorkItem)
        .join(Project, Project.id == WorkItem.project_id)
        .where(WorkItem.is_archived.is_(False), Project.status != "archived", _text_filter(None, q))
        .options(selectinload(WorkItem.labels), selectinload(WorkItem.assignee))
        .order_by(WorkItem.updated_at.desc())
        .limit(limit)
    )
    for it in db.scalars(stmt):
        if it.id not in seen:
            results.append(it)
            seen.add(it.id)
    return results[:limit]


def transitions(db: Session, item: WorkItem) -> list[StatusTransition]:
    return list(
        db.scalars(select(StatusTransition).where(StatusTransition.work_item_id == item.id).order_by(StatusTransition.at))
    )


def my_items(db: Session, user: User) -> tuple[list[WorkItem], list[WorkItem]]:
    """(assigned & not done, subset currently in progress) across active projects, ordered by rank."""
    stmt = (
        select(WorkItem)
        .join(Project, Project.id == WorkItem.project_id)
        .where(WorkItem.assignee_id == user.id, WorkItem.is_archived.is_(False), Project.status != "archived")
        .options(selectinload(WorkItem.labels), selectinload(WorkItem.assignee), selectinload(WorkItem.project))
        .order_by(WorkItem.rank, WorkItem.number)
    )
    assigned: list[WorkItem] = []
    in_progress: list[WorkItem] = []
    for it in db.scalars(stmt):
        cat = status_category(it.project.workflow, it.status)
        if cat == "done":
            continue
        assigned.append(it)
        if cat == "in_progress":
            in_progress.append(it)
    return assigned, in_progress


def mentions_for(db: Session, user: User, limit: int = 10) -> list[Comment]:
    """Recent comments that mention the user by @handle or name (not authored by them)."""
    stmt = (
        select(Comment)
        .where(
            or_(Comment.body.ilike(f"%@{user.handle}%"), Comment.body.ilike(f"%@{user.name}%")),
            or_(Comment.author_id != user.id, Comment.author_id.is_(None)),
        )
        .order_by(Comment.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))
