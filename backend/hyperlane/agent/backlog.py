"""Prompt-driven backlog builder: a goal in, epics -> features -> stories out (then applied in one bulk create)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import Project, User, WorkItem
from . import _compat as c
from .prompts import BACKLOG_SYSTEM, project_context
from .provider import get_provider

log = logging.getLogger(__name__)

Priority = Literal["critical", "high", "medium", "low", "none"]


class DraftItem(BaseModel):
    temp_id: str
    parent_temp_id: str | None = None
    type: str
    title: str
    description: str = ""
    acceptance_criteria: str | None = None
    points: float | None = None
    priority: Priority | None = "medium"
    labels: list[str] = Field(default_factory=list)


class BacklogDraft(BaseModel):
    summary: str
    questions: list[str] = Field(default_factory=list)
    items: list[DraftItem] = Field(default_factory=list)


def _normalize(project: Project, draft: dict[str, Any], parent: WorkItem | None) -> dict[str, Any]:
    """Make the proposal safe: valid types, points on scale, hierarchy that resolves."""
    valid_types = [t["key"] for t in (project.item_types or [])]
    levels = {t["key"]: int(t.get("level", 0)) for t in (project.item_types or [])}
    scale = [float(p) for p in (project.settings or {}).get("points_scale", [1, 2, 3, 5, 8, 13])]
    leaf = c.leaf_type(project)
    items = draft.get("items") or []
    temp_ids = {it.get("temp_id") for it in items}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    parent_level = levels.get(parent.type, -1) if parent else -1
    for i, it in enumerate(items):
        it = dict(it)
        tid = str(it.get("temp_id") or f"t{i + 1}")
        while tid in seen:
            tid += "x"
        seen.add(tid)
        it["temp_id"] = tid
        if valid_types and it.get("type") not in valid_types:
            it["type"] = leaf
        if it.get("parent_temp_id") not in temp_ids:
            it["parent_temp_id"] = None
        if parent and it["parent_temp_id"] is None and levels.get(it["type"], 99) <= parent_level:
            # can't nest an epic under a feature: demote to the next level down
            lower = [k for k, lv in levels.items() if lv > parent_level]
            it["type"] = min(lower, key=lambda k: levels[k]) if lower else leaf
        pts = it.get("points")
        if pts is not None:
            try:
                pts = float(pts)
                it["points"] = min(scale, key=lambda s: abs(s - pts)) if scale else pts
            except (TypeError, ValueError):
                it["points"] = None
        if levels.get(it["type"], 99) < max(levels.values(), default=0):
            it["points"] = None  # containers don't carry points
        it["title"] = str(it.get("title") or "Untitled")[:300]
        it["description"] = it.get("description") or ""
        if it.get("priority") not in ("critical", "high", "medium", "low", "none"):
            it["priority"] = "medium"
        it["labels"] = [str(lb) for lb in (it.get("labels") or [])][:6]
        out.append(it)
    return {"summary": draft.get("summary") or "", "questions": list(draft.get("questions") or []), "items": out}


async def propose(
    db: Session, project: Project, prompt: str, parent_id: str | None, user: User | None
) -> dict[str, Any]:
    """Draft a backlog (BacklogProposal shape). Does not write anything."""
    parent = c.resolve_item(db, parent_id) if parent_id else None
    provider = get_provider()
    levels = sorted((project.item_types or []), key=lambda t: t.get("level", 0))
    type_line = " > ".join(t["key"] for t in levels) or "story"
    lines = [
        project_context(db, project),
        f"Type hierarchy (top to leaf): {type_line}",
        f"Points scale: {(project.settings or {}).get('points_scale', [1, 2, 3, 5, 8, 13])}",
        f"Existing labels you may reuse: {[lb.name for lb in _labels(db, project)][:20]}",
    ]
    if parent:
        lines.append(
            f"Everything you draft will be nested under existing {parent.type} {c.item_key(parent)} "
            f"'{parent.title}'. Only draft items of a lower level than '{parent.type}'; leave parent_temp_id null "
            "for direct children of it."
        )
    if user:
        lines.append(f"Requested by {user.name} ({user.role}).")
    lines.append(f"Request: {prompt.strip()}")
    draft = await provider.complete(BACKLOG_SYSTEM, "\n".join(lines), json_schema=BacklogDraft)
    assert isinstance(draft, dict)
    return _normalize(project, draft, parent)


def _labels(db: Session, project: Project):
    from sqlalchemy import select

    from ..models import Label

    return db.scalars(select(Label).where(Label.project_id == project.id)).all()


def apply(
    db: Session, project: Project, items: list[dict[str, Any]], parent_id: str | None, user: User | None
) -> list[WorkItem]:
    """Create the proposed items via services.items.bulk_create (temp ids build the hierarchy)."""
    parent = c.resolve_item(db, parent_id) if parent_id else None
    specs: list[dict[str, Any]] = []
    for it in items:
        spec = {
            "temp_id": it.get("temp_id"),
            "parent_temp_id": it.get("parent_temp_id"),
            "type": it.get("type"),
            "title": it.get("title"),
            "description": it.get("description"),
            "acceptance_criteria": it.get("acceptance_criteria"),
            "points": it.get("points"),
            "priority": it.get("priority") or "medium",
            "labels": it.get("labels") or [],
            "source": "agent",
        }
        if parent and not spec["parent_temp_id"]:
            spec["parent_id"] = parent.id
        specs.append({k: v for k, v in spec.items() if v is not None or k in ("parent_temp_id",)})
    return c.bulk_create(db, project, specs, user)
