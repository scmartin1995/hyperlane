"""Sprints: create/plan, start (commitment snapshot), close (carry-over, capacity actuals)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import utcnow
from ..models import CapacityEntry, Project, Sprint, SprintCommitment, User, WorkItem
from ..schemas.common import SprintOut
from .activity import record
from .events import bus
from .items import serialize_items
from .templates import status_category


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def list_sprints(db: Session, project_id: str, state: str | None = None) -> list[Sprint]:
    stmt = select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.number.desc())
    if state:
        stmt = stmt.where(Sprint.state == state)
    return list(db.scalars(stmt))


def sprint_items(db: Session, sprint: Sprint) -> list[WorkItem]:
    stmt = (
        select(WorkItem)
        .where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False))
        .options(selectinload(WorkItem.labels), selectinload(WorkItem.assignee))
        .order_by(WorkItem.rank, WorkItem.number)
    )
    return list(db.scalars(stmt))


def create_sprint(db: Session, project: Project, data: dict[str, Any], actor: User | None) -> Sprint:
    """Defaults: number=next, name="Sprint N", start=day after the last sprint's end (or today),
    end=start+sprint_length_days-1. Emits `sprint.created`."""
    last = db.scalar(select(Sprint).where(Sprint.project_id == project.id).order_by(Sprint.number.desc()).limit(1))
    number = (last.number + 1) if last else 1
    length = int(project.settings.get("sprint_length_days") or 14)
    start = _to_date(data.get("start_date"))
    if start is None:
        start = max(last.end_date + timedelta(days=1), date.today()) if last else date.today()
        if last and last.end_date >= date.today():
            start = last.end_date + timedelta(days=1)
    end = _to_date(data.get("end_date")) or (start + timedelta(days=length - 1))
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    sprint = Sprint(
        project_id=project.id,
        number=number,
        name=(data.get("name") or "").strip() or f"Sprint {number}",
        goal=data.get("goal"),
        start_date=start,
        end_date=end,
        capacity_points=data.get("capacity_points"),
        capacity_hours=data.get("capacity_hours"),
        planning_notes=dict(data.get("planning_notes") or {}),
    )
    db.add(sprint)
    db.flush()
    record(
        db, entity_type="sprint", entity_id=sprint.id, action="created", project_id=project.id, actor=actor,
        summary=f"{sprint.name} planned ({start.isoformat()} → {end.isoformat()})",
    )
    db.commit()
    bus.emit("sprint.created", project_id=project.id, entity_type="sprint", entity_id=sprint.id,
             actor_id=actor.id if actor else None)  # fmt: skip
    return sprint


def update_sprint(db: Session, sprint: Sprint, data: dict[str, Any], actor: User | None) -> Sprint:
    changes: dict[str, list[Any]] = {}
    for field in ("name", "goal", "capacity_points", "capacity_hours"):
        if field in data and getattr(sprint, field) != data[field]:
            if field == "name" and not (data[field] or "").strip():
                raise ValueError("name cannot be empty")
            changes[field] = [getattr(sprint, field), data[field]]
            setattr(sprint, field, data[field])
    for field in ("start_date", "end_date"):
        if data.get(field) is not None:
            value = _to_date(data[field])
            if getattr(sprint, field) != value:
                changes[field] = [getattr(sprint, field), value]
                setattr(sprint, field, value)
    if sprint.end_date < sprint.start_date:
        raise ValueError("end_date must be on or after start_date")
    if data.get("planning_notes") is not None:
        sprint.planning_notes = {**(sprint.planning_notes or {}), **data["planning_notes"]}
        changes.setdefault("planning_notes", ["…", "…"])
    if changes:
        record(
            db, entity_type="sprint", entity_id=sprint.id, action="updated", project_id=sprint.project_id,
            actor=actor, summary=f"{sprint.name} updated ({', '.join(changes)})", changes=changes,
        )
    db.commit()
    bus.emit("sprint.updated", project_id=sprint.project_id, entity_type="sprint", entity_id=sprint.id,
             actor_id=actor.id if actor else None, data={"changes": list(changes)})  # fmt: skip
    return sprint


def delete_sprint(db: Session, sprint: Sprint, actor: User | None) -> None:
    """Only planned sprints can be deleted; their items go back to the backlog (unscheduled)."""
    if sprint.state != "planned":
        raise ValueError("only planned sprints can be deleted")
    pid, sid, name = sprint.project_id, sprint.id, sprint.name
    for item in sprint_items(db, sprint):
        item.sprint_id = None
    db.delete(sprint)
    record(db, entity_type="sprint", entity_id=sid, action="deleted", project_id=pid, actor=actor,
           summary=f"{name} deleted")  # fmt: skip
    db.commit()
    bus.emit("sprint.updated", project_id=pid, entity_type="sprint", entity_id=sid,
             actor_id=actor.id if actor else None, data={"deleted": True})  # fmt: skip


def _upsert_capacity(db: Session, sprint: Sprint, user_id: str) -> CapacityEntry:
    entry = db.scalar(
        select(CapacityEntry).where(CapacityEntry.sprint_id == sprint.id, CapacityEntry.user_id == user_id)
    )
    if entry is None:
        entry = CapacityEntry(sprint_id=sprint.id, user_id=user_id)
        db.add(entry)
        db.flush()
    return entry


def start_sprint(db: Session, sprint: Sprint, actor: User | None) -> Sprint:
    """Only one active sprint per project. Snapshots SprintCommitment rows, committed_points/count and
    per-assignee planned capacity. Emits `sprint.started`."""
    if sprint.state != "planned":
        raise ValueError(f"sprint is {sprint.state}; only planned sprints can start")
    other = db.scalar(
        select(Sprint).where(Sprint.project_id == sprint.project_id, Sprint.state == "active", Sprint.id != sprint.id)
    )
    if other:
        raise ValueError(f"{other.name} is still active; close it first")
    now = utcnow()
    items = sprint_items(db, sprint)
    planned: dict[str, list[float]] = {}
    for it in items:
        db.add(SprintCommitment(sprint_id=sprint.id, work_item_id=it.id, points=it.points, added_at=now))
        if it.assignee_id:
            planned.setdefault(it.assignee_id, [0.0, 0])
            planned[it.assignee_id][0] += it.points or 0.0
            planned[it.assignee_id][1] += 1
    sprint.committed_points = float(sum(it.points or 0.0 for it in items))
    sprint.committed_count = len(items)
    for uid, (pts, cnt) in planned.items():
        entry = _upsert_capacity(db, sprint, uid)
        if not entry.planned_points and not entry.planned_count:
            entry.planned_points, entry.planned_count = pts, int(cnt)
    sprint.state = "active"
    sprint.start_date = min(sprint.start_date, date.today())
    record(
        db, entity_type="sprint", entity_id=sprint.id, action="started", project_id=sprint.project_id, actor=actor,
        summary=f"{sprint.name} started with {sprint.committed_count} items / {sprint.committed_points:g} points",
    )
    db.commit()
    bus.emit(
        "sprint.started", project_id=sprint.project_id, entity_type="sprint", entity_id=sprint.id,
        actor_id=actor.id if actor else None,
        data={"committed_points": sprint.committed_points, "committed_count": sprint.committed_count},
    )  # fmt: skip
    return sprint


def close_sprint(db: Session, sprint: Sprint, carry_over: str, actor: User | None) -> dict[str, Any]:
    """Close an active sprint. `carry_over`: "next" (next planned sprint, created if missing), "backlog"
    (unschedule) or a sprint id. Returns `{"sprint", "carried", "completed"}` as JSON-ready dicts."""
    if sprint.state != "active":
        raise ValueError(f"sprint is {sprint.state}; only active sprints can be closed")
    project = sprint.project
    items = sprint_items(db, sprint)
    done_items = [it for it in items if status_category(project.workflow, it.status) == "done"]
    open_items = [it for it in items if status_category(project.workflow, it.status) != "done"]

    target: Sprint | None = None
    if open_items:
        if carry_over == "next":
            target = db.scalar(
                select(Sprint)
                .where(Sprint.project_id == project.id, Sprint.state == "planned", Sprint.number > sprint.number)
                .order_by(Sprint.number)
            )
            if target is None:
                target = _next_sprint(db, project, sprint, actor)
        elif carry_over == "backlog":
            target = None
        else:
            target = db.get(Sprint, carry_over)
            if target is None or target.project_id != project.id or target.state == "closed":
                raise ValueError("carry_over must be 'next', 'backlog' or the id of an open sprint of this project")
    for it in open_items:
        it.sprint_id = target.id if target else None
        it.updated_at = utcnow()

    sprint.completed_points = float(sum(it.points or 0.0 for it in done_items))
    sprint.completed_count = len(done_items)

    # capacity actuals per assignee (planned from commitments if the entry didn't exist)
    committed = {
        c.work_item_id: c for c in db.scalars(select(SprintCommitment).where(SprintCommitment.sprint_id == sprint.id))
    }
    per_user: dict[str, dict[str, float]] = {}
    for it in items:
        if not it.assignee_id:
            continue
        acc = per_user.setdefault(it.assignee_id, {"cp": 0.0, "cc": 0, "pp": 0.0, "pc": 0})
        if it in done_items:
            acc["cp"] += it.points or 0.0
            acc["cc"] += 1
        if it.id in committed:
            acc["pp"] += committed[it.id].points or 0.0
            acc["pc"] += 1
    for uid, acc in per_user.items():
        entry = _upsert_capacity(db, sprint, uid)
        entry.completed_points, entry.completed_count = acc["cp"], int(acc["cc"])
        if not entry.planned_points and not entry.planned_count:
            entry.planned_points, entry.planned_count = acc["pp"], int(acc["pc"])

    sprint.state = "closed"
    sprint.closed_at = utcnow()
    record(
        db, entity_type="sprint", entity_id=sprint.id, action="closed", project_id=project.id, actor=actor,
        summary=f"{sprint.name} closed: {sprint.completed_count}/{sprint.committed_count} items, "
        f"{sprint.completed_points:g}/{sprint.committed_points:g} points; {len(open_items)} carried",
        changes={"carried": [None, [it.id for it in open_items]]},
    )
    db.commit()
    try:
        from .capacity import learn_from_sprint  # owner: backend-analytics

        learn_from_sprint(db, sprint)
        db.commit()
    except ImportError:
        pass
    bus.emit(
        "sprint.closed", project_id=project.id, entity_type="sprint", entity_id=sprint.id,
        actor_id=actor.id if actor else None,
        data={
            "completed_points": sprint.completed_points, "completed_count": sprint.completed_count,
            "carried": len(open_items), "carry_target": target.id if target else None,
        },
    )  # fmt: skip
    if target is not None and carry_over == "next":
        bus.emit("sprint.updated", project_id=project.id, entity_type="sprint", entity_id=target.id)
    return {
        "sprint": SprintOut.model_validate(sprint).model_dump(mode="json"),
        "carried": [o.model_dump(mode="json") for o in serialize_items(open_items, db)],
        "completed": [o.model_dump(mode="json") for o in serialize_items(done_items, db)],
    }


def _next_sprint(db: Session, project: Project, after: Sprint, actor: User | None) -> Sprint:
    """Create the sprint that follows `after` (no commit; caller commits)."""
    max_number = db.scalar(select(func.max(Sprint.number)).where(Sprint.project_id == project.id)) or after.number
    number = int(max_number) + 1
    length = int(project.settings.get("sprint_length_days") or 14)
    start = max(after.end_date + timedelta(days=1), date.today())
    sprint = Sprint(
        project_id=project.id, number=number, name=f"Sprint {number}", start_date=start,
        end_date=start + timedelta(days=length - 1),
    )  # fmt: skip
    db.add(sprint)
    db.flush()
    record(db, entity_type="sprint", entity_id=sprint.id, action="created", project_id=project.id, actor=actor,
           summary=f"{sprint.name} planned for carry-over")  # fmt: skip
    return sprint
