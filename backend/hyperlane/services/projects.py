"""Projects: templates applied, keys derived, labels, summary, workflow migrations."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Label, Project, Sprint, StatusTransition, User, WorkItem
from ..schemas.common import ProjectOut, SprintOut, UserBrief
from .activity import record
from .events import bus
from .templates import CATEGORIES, default_evm, get_template

_PROJECT_FIELDS = {
    "name", "description", "methodology", "status", "color", "icon", "lead_id", "slack_channel",
    "teams_webhook_override", "item_types", "workflow", "settings", "evm",
}  # fmt: skip
STATUSES = {"active", "paused", "done", "archived"}


# ---------- keys ----------


def derive_key(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words:
        return "PRJ"
    if len(words) == 1:
        w = words[0].upper()
        return (w[:3] if len(w) >= 3 else w) or "PRJ"
    return "".join(w[0] for w in words).upper()[:5]


def unique_key(db: Session, base: str, *, exclude_id: str | None = None) -> str:
    base = re.sub(r"[^A-Z0-9]", "", base.upper())[:8] or "PRJ"
    candidate = base
    n = 2
    while True:
        stmt = select(Project.id).where(Project.key == candidate)
        if exclude_id:
            stmt = stmt.where(Project.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}{n}"
        n += 1


# ---------- validation ----------


def validate_item_types(item_types: list[dict]) -> list[dict]:
    if not item_types:
        raise ValueError("a project needs at least one item type")
    keys: set[str] = set()
    for t in item_types:
        key = str(t.get("key") or "").strip()
        if not key:
            raise ValueError("item type key is required")
        if key in keys:
            raise ValueError(f"duplicate item type key: {key}")
        keys.add(key)
        t.setdefault("name", key.title())
        t.setdefault("plural", t["name"] + "s")
        t.setdefault("icon", "📝")
        t.setdefault("color", "#27cfc3")
        t.setdefault("level", 0)
    return item_types


def validate_workflow(workflow: list[dict]) -> list[dict]:
    if not workflow:
        raise ValueError("a workflow needs at least one state")
    keys: set[str] = set()
    cats: set[str] = set()
    for s in workflow:
        key = str(s.get("key") or "").strip()
        if not key:
            raise ValueError("workflow state key is required")
        if key in keys:
            raise ValueError(f"duplicate workflow state key: {key}")
        if s.get("category") not in CATEGORIES:
            raise ValueError(f"workflow state {key}: category must be one of {', '.join(CATEGORIES)}")
        keys.add(key)
        cats.add(s["category"])
        s.setdefault("name", key.replace("_", " ").title())
        s.setdefault("wip_limit", None)
        s.setdefault("color", "#676767")
    if "todo" not in cats or "done" not in cats:
        raise ValueError("a workflow needs at least one 'todo' and one 'done' state")
    return workflow


# ---------- CRUD ----------


def create_project(db: Session, data: dict[str, Any], actor: User | None) -> Project:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    template_key = data.get("template") or "custom"
    tpl = get_template(template_key)

    project = Project(
        name=name,
        key=unique_key(db, data.get("key") or derive_key(name)),
        description=data.get("description"),
        template=template_key,
        methodology=data.get("methodology") or tpl["methodology"],
        color=data.get("color") or "#e4b963",
        icon=data.get("icon") or tpl["icon"],
        item_types=validate_item_types(data.get("item_types") or tpl["item_types"]),
        workflow=validate_workflow(data.get("workflow") or tpl["workflow"]),
        settings={**tpl["settings"], **(data.get("settings") or {})},
        evm={**default_evm(), **(data.get("evm") or {})},
        lead_id=data.get("lead_id") or (actor.id if actor else None),
        slack_channel=data.get("slack_channel"),
    )
    if project.settings.get("default_type") not in {t["key"] for t in project.item_types}:
        project.settings["default_type"] = project.item_types[-1]["key"]
    db.add(project)
    db.flush()
    label_names = data.get("labels") if data.get("labels") is not None else tpl.get("labels", [])
    for ln in label_names or []:
        if ln and ln.strip():
            db.add(Label(project_id=project.id, name=ln.strip()[:60]))
    record(
        db, entity_type="project", entity_id=project.id, action="created", project_id=project.id, actor=actor,
        summary=f"Project {project.name} ({project.key}) created from template {template_key}",
    )
    db.commit()
    bus.emit("project.created", project_id=project.id, entity_type="project", entity_id=project.id,
             actor_id=actor.id if actor else None)  # fmt: skip
    return project


def update_project(db: Session, project: Project, data: dict[str, Any], actor: User | None) -> Project:
    changes: dict[str, list[Any]] = {}
    rename: dict[str, str] = data.get("workflow_rename") or {}

    if data.get("key") and data["key"] != project.key:
        changes["key"] = [project.key, unique_key(db, data["key"], exclude_id=project.id)]
        project.key = changes["key"][1]

    for field in _PROJECT_FIELDS:
        if field not in data or data[field] is None:
            continue
        value = data[field]
        if field == "name" and not str(value).strip():
            raise ValueError("name cannot be empty")
        if field == "status" and value not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(STATUSES))}")
        if field == "item_types":
            value = validate_item_types(value)
        if field == "workflow":
            value = validate_workflow(value)
        if field == "settings":
            value = {**(project.settings or {}), **value}
        if field == "evm":
            value = {**default_evm(), **(project.evm or {}), **value}
        old = getattr(project, field)
        if old != value:
            changes[field] = [old, value] if field not in {"item_types", "workflow", "settings", "evm"} else ["…", "…"]
            setattr(project, field, value)

    if rename:
        _migrate_statuses(db, project, rename)
        changes["workflow_rename"] = [list(rename.keys()), list(rename.values())]

    if changes:
        record(
            db, entity_type="project", entity_id=project.id, action="updated", project_id=project.id, actor=actor,
            summary=f"Project {project.name} updated ({', '.join(changes)})", changes=changes,
        )
    db.commit()
    bus.emit("project.updated", project_id=project.id, entity_type="project", entity_id=project.id,
             actor_id=actor.id if actor else None, data={"changes": list(changes)})  # fmt: skip
    return project


def _migrate_statuses(db: Session, project: Project, rename: dict[str, str]) -> None:
    valid = {s["key"] for s in project.workflow}
    for old, new in rename.items():
        if new not in valid:
            raise ValueError(f"workflow_rename: '{new}' is not a state of the project's workflow")
        for item in db.scalars(select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.status == old)):
            item.status = new
        for tr in db.scalars(
            select(StatusTransition).where(StatusTransition.project_id == project.id, StatusTransition.to_status == old)
        ):
            tr.to_status = new
        for tr in db.scalars(
            select(StatusTransition).where(
                StatusTransition.project_id == project.id, StatusTransition.from_status == old
            )
        ):
            tr.from_status = new


def archive_project(db: Session, project: Project, actor: User | None) -> Project:
    project.status = "archived"
    record(
        db, entity_type="project", entity_id=project.id, action="archived", project_id=project.id, actor=actor,
        summary=f"Project {project.name} archived",
    )
    db.commit()
    bus.emit("project.deleted", project_id=project.id, entity_type="project", entity_id=project.id,
             actor_id=actor.id if actor else None)  # fmt: skip
    return project


def list_projects(db: Session) -> list[Project]:
    stmt = select(Project).order_by((Project.status == "archived").asc(), Project.created_at.asc())
    return list(db.scalars(stmt))


# ---------- labels ----------


def list_labels(db: Session, project_id: str) -> list[Label]:
    return list(db.scalars(select(Label).where(Label.project_id == project_id).order_by(Label.name)))


def create_label(db: Session, project: Project, name: str, color: str | None = None) -> Label:
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("label name is required")
    existing = db.scalar(select(Label).where(Label.project_id == project.id, Label.name == name))
    if existing:
        raise ValueError(f"label '{name}' already exists")
    label = Label(project_id=project.id, name=name, color=color or "#6b3a8e")
    db.add(label)
    db.commit()
    bus.emit("project.updated", project_id=project.id, entity_type="label", entity_id=label.id)
    return label


def update_label(db: Session, label: Label, data: dict[str, Any]) -> Label:
    if data.get("name"):
        name = data["name"].strip()[:60]
        dup = db.scalar(
            select(Label).where(Label.project_id == label.project_id, Label.name == name, Label.id != label.id)
        )
        if dup:
            raise ValueError(f"label '{name}' already exists")
        label.name = name
    if data.get("color"):
        label.color = data["color"]
    db.commit()
    bus.emit("project.updated", project_id=label.project_id, entity_type="label", entity_id=label.id)
    return label


def delete_label(db: Session, label: Label) -> None:
    pid = label.project_id
    db.delete(label)
    db.commit()
    bus.emit("project.updated", project_id=pid, entity_type="label", entity_id=label.id)


# ---------- summary ----------


def project_summary(db: Session, project: Project) -> dict[str, Any]:
    """Matches `ProjectSummary` in frontend/src/api/types.ts."""
    live = select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.is_archived.is_(False))
    done_keys = {s["key"] for s in project.workflow if s["category"] == "done"}

    by_status = {
        k: int(v) for k, v in db.execute(
            select(WorkItem.status, func.count()).where(live.whereclause).group_by(WorkItem.status)
        )
    }  # fmt: skip
    by_type = {
        k: int(v) for k, v in db.execute(
            select(WorkItem.type, func.count()).where(live.whereclause).group_by(WorkItem.type)
        )
    }  # fmt: skip
    counts_by_status = {s["key"]: by_status.get(s["key"], 0) for s in project.workflow}
    for k, v in by_status.items():
        counts_by_status.setdefault(k, v)

    total_items = sum(by_status.values())
    done_items = sum(v for k, v in by_status.items() if k in done_keys)
    total_points = float(db.scalar(select(func.coalesce(func.sum(WorkItem.points), 0.0)).where(live.whereclause)) or 0)
    done_points = 0.0
    if done_keys:
        done_points = float(
            db.scalar(
                select(func.coalesce(func.sum(WorkItem.points), 0.0)).where(
                    live.whereclause, WorkItem.status.in_(done_keys)
                )
            )
            or 0
        )
    blocked = int(db.scalar(select(func.count()).select_from(WorkItem).where(live.whereclause, WorkItem.blocked.is_(True))) or 0)
    overdue_stmt = select(func.count()).select_from(WorkItem).where(
        live.whereclause, WorkItem.due_date < date.today(), WorkItem.status.not_in(done_keys) if done_keys else True
    )
    overdue = int(db.scalar(overdue_stmt) or 0)

    active = db.scalar(
        select(Sprint).where(Sprint.project_id == project.id, Sprint.state == "active").order_by(Sprint.number)
    )
    nxt = db.scalar(
        select(Sprint).where(Sprint.project_id == project.id, Sprint.state == "planned").order_by(Sprint.number)
    )

    member_ids: set[str] = set()
    for (uid,) in db.execute(select(WorkItem.assignee_id).where(live.whereclause, WorkItem.assignee_id.is_not(None)).distinct()):
        member_ids.add(uid)
    if project.lead_id:
        member_ids.add(project.lead_id)
    members = list(db.scalars(select(User).where(User.id.in_(member_ids)).order_by(User.name))) if member_ids else []

    return {
        "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        "counts_by_status": counts_by_status,
        "counts_by_type": {t["key"]: by_type.get(t["key"], 0) for t in project.item_types} | by_type,
        "total_items": total_items,
        "done_items": done_items,
        "total_points": total_points,
        "done_points": done_points,
        "active_sprint": SprintOut.model_validate(active).model_dump(mode="json") if active else None,
        "next_sprint": SprintOut.model_validate(nxt).model_dump(mode="json") if nxt else None,
        "members": [UserBrief.model_validate(u).model_dump(mode="json") for u in members],
        "blocked": blocked,
        "overdue": overdue,
    }


def touch(project: Project) -> None:
    project.updated_at = utcnow()
