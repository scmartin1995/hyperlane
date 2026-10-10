"""Tools the business-analyst agent can call.

Each tool is a plain function `fn(db, user, **input) -> dict | list | str` that runs inside
`session_scope()` (see `execute`). Business logic lives in the other slices' services; tools
only resolve references, call those services (lazily imported) and shape compact results.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import ActionItem, IntakeRequest, Project, Sprint, User, WorkItem
from ..services.events import bus
from . import _compat as c
from ._compat import NotAvailable

log = logging.getLogger(__name__)

MAX_LIST = 50


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]
    mutating: bool = False
    tags: list[str] = field(default_factory=list)

    def anthropic(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, schema: dict[str, Any] | None = None, *, mutating: bool = False):
    props = schema or {}
    required = [k for k, v in props.items() if v.pop("required", False)]
    input_schema = {"type": "object", "properties": props, "required": required}

    def deco(fn):
        REGISTRY[name] = ToolSpec(name, description, input_schema, fn, mutating=mutating)
        return fn

    return deco


def available_tools(*, slack: bool | None = None) -> list[ToolSpec]:
    """Tools to expose for a run. Slack posting only shows up when Slack is configured."""
    if slack is None:
        slack = get_settings().slack_enabled
    return [t for t in REGISTRY.values() if t.name != "send_slack_message" or slack]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclass
class ToolOutcome:
    ok: bool
    result: Any
    summary: str

    def as_text(self, limit: int = 12000) -> str:
        if isinstance(self.result, str):
            text = self.result
        else:
            text = json.dumps(self.result, default=str, ensure_ascii=False)
        return text if len(text) <= limit else text[:limit] + " …(truncated)"


def execute(spec: ToolSpec, user_id: str | None, tool_input: dict[str, Any] | None) -> ToolOutcome:
    """Run one tool inside its own DB session. Never raises: errors become `ok=False` results."""
    tool_input = dict(tool_input or {})
    try:
        with session_scope() as db:
            user = db.get(User, user_id) if user_id else None
            result = spec.fn(db, user, **tool_input)
            summary = summarize(spec.name, result)
            # make sure lazy attributes are loaded before the session closes
            json.dumps(result, default=str)
            return ToolOutcome(True, result, summary)
    except NotAvailable as exc:
        return ToolOutcome(False, {"error": str(exc), "hint": "That capability isn't wired up yet."}, str(exc))
    except TypeError as exc:
        log.warning("tool %s got bad input: %s", spec.name, exc)
        return ToolOutcome(False, {"error": f"Bad input for {spec.name}: {exc}"}, f"bad input: {exc}")
    except Exception as exc:
        log.exception("tool %s failed", spec.name)
        return ToolOutcome(False, {"error": f"{exc.__class__.__name__}: {exc}"}, f"{exc.__class__.__name__}: {exc}")


def summarize(name: str, result: Any) -> str:
    if isinstance(result, dict):
        if "error" in result:
            return str(result["error"])[:200]
        if "summary" in result and isinstance(result["summary"], str):
            return result["summary"][:200]
        if "items" in result and isinstance(result["items"], list):
            return f"{len(result['items'])} item(s)"
        if "key" in result and "title" in result:
            return f"{result['key']} {result['title']}"[:200]
        return ", ".join(f"{k}={v}" for k, v in list(result.items())[:4] if not isinstance(v, (dict, list)))[:200]
    if isinstance(result, list):
        return f"{len(result)} result(s)"
    return str(result)[:200]


# ---------------------------------------------------------------------------
# Projects / items
# ---------------------------------------------------------------------------


def _project(db: Session, ref: str | None) -> Project:
    proj = c.resolve_project(db, ref)
    if proj is None:
        raise ValueError(f"Project {ref!r} not found. Use list_projects to see the options.")
    return proj


def _item(db: Session, ref: str) -> WorkItem:
    item = c.resolve_item(db, ref)
    if item is None:
        raise ValueError(f"Item {ref!r} not found (use an id or a key like HL-12).")
    return item


@tool("list_projects", "List all projects with key, name, methodology, item types and workflow states.")
def list_projects(db: Session, user: User | None) -> list[dict]:
    rows = db.scalars(select(Project).where(Project.status != "archived").order_by(Project.created_at)).all()
    return [
        {
            "id": p.id,
            "key": p.key,
            "name": p.name,
            "methodology": p.methodology,
            "status": p.status,
            "item_types": [t["key"] for t in p.item_types or []],
            "workflow": [s["key"] for s in p.workflow or []],
            "estimation": (p.settings or {}).get("estimation"),
        }
        for p in rows
    ]


@tool(
    "search_items",
    "Full-text search over work items (title/description/key). Use this before creating items to avoid "
    "duplicates and to find the item the user is talking about.",
    {
        "query": {"type": "string", "description": "Search text or an item key like HL-12", "required": True},
        "project_id": {"type": "string", "description": "Optional project id or key to narrow the search"},
    },
)
def search_items(db: Session, user: User | None, query: str, project_id: str | None = None) -> dict:
    proj = c.resolve_project(db, project_id) if project_id else None
    try:
        fn = c.service("items", "search_items")
        rows = c.call_adaptive(fn, db=db, q=query, query=query, project_id=proj.id if proj else None, limit=MAX_LIST)
        rows = [r for r in rows if proj is None or getattr(r, "project_id", proj.id) == proj.id][:MAX_LIST]
    except NotAvailable:
        direct = c.resolve_item(db, query)
        if direct is not None:
            rows = [direct]
        else:
            stmt = (
                select(WorkItem)
                .where(WorkItem.is_archived.is_(False))
                .where(or_(WorkItem.title.ilike(f"%{query}%"), WorkItem.description.ilike(f"%{query}%")))
                .order_by(WorkItem.rank)
                .limit(MAX_LIST)
            )
            if proj:
                stmt = stmt.where(WorkItem.project_id == proj.id)
            rows = db.scalars(stmt).all()
    items = [c.serialize_item(db, r) if isinstance(r, WorkItem) else c._compact(r) for r in rows]
    return {"query": query, "items": items}


@tool(
    "list_items",
    "List work items in a project with optional filters. Returns compact rows ordered by backlog rank.",
    {
        "project_id": {"type": "string", "required": True},
        "status": {"type": "string", "description": "workflow state key"},
        "type": {"type": "string", "description": "item type key (epic, feature, story, bug ...)"},
        "sprint_id": {"type": "string"},
        "assignee_id": {"type": "string", "description": "user id, handle or name"},
        "unscheduled": {"type": "boolean", "description": "only items not in any sprint"},
        "parent_id": {"type": "string", "description": "only children of this item"},
        "include_done": {"type": "boolean", "description": "default false"},
        "limit": {"type": "integer", "description": "max rows (default 50)"},
    },
)
def list_items(
    db: Session,
    user: User | None,
    project_id: str,
    status: str | None = None,
    type: str | None = None,
    sprint_id: str | None = None,
    assignee_id: str | None = None,
    unscheduled: bool | None = None,
    parent_id: str | None = None,
    include_done: bool = False,
    limit: int = MAX_LIST,
) -> dict:
    proj = _project(db, project_id)
    assignee = c.resolve_user(db, assignee_id) if assignee_id else None
    limit = max(1, min(int(limit or MAX_LIST), 200))
    done_states = {s["key"] for s in proj.workflow or [] if s.get("category") == "done"}
    stmt = (
        select(WorkItem)
        .where(WorkItem.project_id == proj.id, WorkItem.is_archived.is_(False))
        .order_by(WorkItem.rank, WorkItem.number)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(WorkItem.status == status)
    elif not include_done and done_states:
        stmt = stmt.where(WorkItem.status.not_in(done_states))
    if type:
        stmt = stmt.where(WorkItem.type == type)
    if sprint_id:
        stmt = stmt.where(WorkItem.sprint_id == sprint_id)
    if unscheduled:
        stmt = stmt.where(WorkItem.sprint_id.is_(None))
    if assignee:
        stmt = stmt.where(WorkItem.assignee_id == assignee.id)
    if parent_id:
        parent = _item(db, parent_id)
        stmt = stmt.where(WorkItem.parent_id == parent.id)
    rows = db.scalars(stmt).all()
    return {"project": proj.key, "count": len(rows), "items": [c.serialize_item(db, r) for r in rows]}


@tool(
    "get_item",
    "Get the full detail of one work item (description, acceptance criteria, children, recent comments).",
    {"id_or_key": {"type": "string", "required": True}},
)
def get_item(db: Session, user: User | None, id_or_key: str) -> dict:
    item = _item(db, id_or_key)
    data = c.serialize_item(db, item, compact=False)
    data["parent"] = c.serialize_item(db, item.parent) if item.parent else None
    data["children"] = [c.serialize_item(db, ch) for ch in item.children if not ch.is_archived]
    data["sprint"] = item.sprint.name if item.sprint else None
    data["comments"] = [
        {
            "author": cm.author.name if cm.author else cm.author_name,
            "body": cm.body[:600],
            "is_decision": cm.is_decision,
            "at": cm.created_at.isoformat(),
        }
        for cm in sorted(item.comments, key=lambda x: x.created_at)[-8:]
    ]
    return data


_ITEM_PROPS = {
    "temp_id": {"type": "string", "description": "your own id, used by children as parent_temp_id"},
    "parent_temp_id": {"type": "string"},
    "type": {"type": "string"},
    "title": {"type": "string"},
    "description": {"type": "string"},
    "acceptance_criteria": {"type": "string", "description": "markdown, Given/When/Then"},
    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low", "none"]},
    "points": {"type": "number"},
    "status": {"type": "string"},
    "labels": {"type": "array", "items": {"type": "string"}},
    "assignee_id": {"type": "string"},
    "sprint_id": {"type": "string"},
    "due_date": {"type": "string", "description": "YYYY-MM-DD"},
    "business_value": {"type": "integer"},
}


@tool(
    "create_items",
    "Create one or more work items in a project. Build hierarchies with temp_id/parent_temp_id "
    "(epic -> feature -> story). Only call after the user confirmed what to create.",
    {
        "project_id": {"type": "string", "required": True},
        "items": {
            "type": "array",
            "required": True,
            "items": {"type": "object", "properties": _ITEM_PROPS, "required": ["title"]},
        },
        "parent_id": {"type": "string", "description": "existing item id/key to nest every root item under"},
    },
    mutating=True,
)
def create_items(
    db: Session, user: User | None, project_id: str, items: list[dict], parent_id: str | None = None
) -> dict:
    proj = _project(db, project_id)
    parent = _item(db, parent_id) if parent_id else None
    specs: list[dict[str, Any]] = []
    for raw in items:
        spec = {k: v for k, v in dict(raw).items() if k in _ITEM_PROPS}
        spec["source"] = "agent"
        if spec.get("assignee_id"):
            u = c.resolve_user(db, spec["assignee_id"])
            spec["assignee_id"] = u.id if u else None
        if parent and not spec.get("parent_temp_id"):
            spec["parent_id"] = parent.id
        specs.append(spec)
    created = c.bulk_create(db, proj, specs, user)
    db.flush()
    return {"created": [c.serialize_item(db, it) for it in created], "summary": f"created {len(created)} item(s)"}


@tool(
    "update_item",
    "Update fields of an existing item (status, points, priority, title, description, acceptance_criteria, "
    "assignee_id, sprint_id, labels, blocked, blocked_reason, due_date, parent_id). Confirm with the user first "
    "when changing more than one item.",
    {
        "id_or_key": {"type": "string", "required": True},
        "patch": {"type": "object", "required": True, "description": "fields to change"},
    },
    mutating=True,
)
def update_item(db: Session, user: User | None, id_or_key: str, patch: dict) -> dict:
    item = _item(db, id_or_key)
    patch = dict(patch or {})
    if patch.get("assignee_id"):
        u = c.resolve_user(db, patch["assignee_id"])
        if u is None:
            raise ValueError(f"Assignee {patch['assignee_id']!r} not found")
        patch["assignee_id"] = u.id
    if patch.get("parent_id"):
        patch["parent_id"] = _item(db, patch["parent_id"]).id
    fn = c.service("items", "update_item")
    updated = c.call_adaptive(
        fn, db=db, item=item, item_id=item.id, id=item.id, patch=patch, data=patch, user=user, actor=user
    )
    db.flush()
    target = updated if isinstance(updated, WorkItem) else item
    return {**c.serialize_item(db, target), "summary": f"updated {c.item_key(target)}: {', '.join(patch)}"}


@tool(
    "add_comment",
    "Add a comment (markdown) to a work item on behalf of the agent.",
    {"id_or_key": {"type": "string", "required": True}, "body": {"type": "string", "required": True}},
    mutating=True,
)
def add_comment(db: Session, user: User | None, id_or_key: str, body: str) -> dict:
    item = _item(db, id_or_key)
    fn = c.service("items", "add_comment")
    comment = c.call_adaptive(
        fn,
        db=db,
        item=item,
        item_id=item.id,
        body=body,
        user=user,
        actor=user,
        author=user,
        source="agent",
    )
    db.flush()
    cid = getattr(comment, "id", None)
    return {"comment_id": cid, "item": c.item_key(item), "summary": f"commented on {c.item_key(item)}"}


# ---------------------------------------------------------------------------
# Sprints / planning
# ---------------------------------------------------------------------------


def _sprint_dict(s: Sprint) -> dict:
    return {
        "id": s.id,
        "number": s.number,
        "name": s.name,
        "goal": s.goal,
        "state": s.state,
        "start_date": s.start_date.isoformat(),
        "end_date": s.end_date.isoformat(),
        "committed_points": s.committed_points,
        "completed_points": s.completed_points,
        "committed_count": s.committed_count,
        "completed_count": s.completed_count,
        "capacity_points": s.capacity_points,
    }


@tool("list_sprints", "List a project's sprints (newest first).", {"project_id": {"type": "string", "required": True}})
def list_sprints(db: Session, user: User | None, project_id: str) -> list[dict]:
    proj = _project(db, project_id)
    rows = db.scalars(select(Sprint).where(Sprint.project_id == proj.id).order_by(Sprint.number.desc())).all()
    return [_sprint_dict(s) for s in rows]


@tool(
    "sprint_summary",
    "Summary of one sprint: goal, dates, items grouped by status, committed vs completed points.",
    {"sprint_id": {"type": "string", "required": True}},
)
def sprint_summary(db: Session, user: User | None, sprint_id: str) -> dict:
    sprint = db.get(Sprint, sprint_id)
    if sprint is None:
        raise ValueError(f"Sprint {sprint_id!r} not found")
    proj = sprint.project
    rows = db.scalars(
        select(WorkItem).where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False)).order_by(WorkItem.rank)
    ).all()
    by_status: dict[str, list[dict]] = {}
    for it in rows:
        by_status.setdefault(it.status, []).append(c.serialize_item(db, it))
    done_states = {s["key"] for s in proj.workflow or [] if s.get("category") == "done"}
    done_points = sum((it.points or 0) for it in rows if it.status in done_states)
    total_points = sum((it.points or 0) for it in rows)
    return {
        **_sprint_dict(sprint),
        "project": proj.key,
        "days_left": max(0, (sprint.end_date - c.today()).days) if sprint.state == "active" else None,
        "items_total": len(rows),
        "points_total": total_points,
        "points_done": done_points,
        "blocked": [c.item_key(it) for it in rows if it.blocked],
        "by_status": by_status,
    }


@tool(
    "plan_suggestion",
    "Ask the planner for a sprint plan suggestion (ranked candidates that fit the team's learned capacity).",
    {"sprint_id": {"type": "string", "required": True}},
)
def plan_suggestion(db: Session, user: User | None, sprint_id: str) -> Any:
    sprint = db.get(Sprint, sprint_id)
    if sprint is None:
        raise ValueError(f"Sprint {sprint_id!r} not found")
    fn = c.service("capacity", "suggest_plan")
    return _plain(c.call_adaptive(fn, db=db, sprint=sprint, sprint_id=sprint.id))


@tool(
    "list_people",
    "List team members (name, handle, role, skills, hours/week). Optionally only people active on a project.",
    {"project_id": {"type": "string"}},
)
def list_people(db: Session, user: User | None, project_id: str | None = None) -> list[dict]:
    rows = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
    if project_id:
        proj = _project(db, project_id)
        ids = set(
            db.scalars(
                select(WorkItem.assignee_id).where(WorkItem.project_id == proj.id, WorkItem.assignee_id.is_not(None))
            ).all()
        )
        if proj.lead_id:
            ids.add(proj.lead_id)
        if ids:
            rows = [u for u in rows if u.id in ids]
    return [
        {
            "id": u.id,
            "name": u.name,
            "handle": u.handle,
            "role": u.role,
            "skills": u.skills,
            "hours_per_week": u.hours_per_week,
            "focus_factor": u.focus_factor,
        }
        for u in rows
    ]


@tool(
    "capacity",
    "Learned capacity profiles for a project's people (avg points per sprint, commitment accuracy) and the "
    "active sprint's capacity if there is one.",
    {"project_id": {"type": "string", "required": True}},
)
def capacity(db: Session, user: User | None, project_id: str) -> dict:
    proj = _project(db, project_id)
    from ..models import CapacityProfile

    profiles = db.scalars(select(CapacityProfile).where(CapacityProfile.project_id == proj.id)).all()
    out: dict[str, Any] = {
        "profiles": [
            {
                "user": (db.get(User, p.user_id).name if db.get(User, p.user_id) else p.user_id),
                "sprints_observed": p.sprints_observed,
                "avg_points": p.avg_points,
                "avg_count": p.avg_count,
                "commitment_accuracy": p.commitment_accuracy,
                "confidence": p.confidence,
                "insights": p.insights,
            }
            for p in profiles
        ]
    }
    sprint = c.active_sprint(db, proj.id)
    if sprint:
        try:
            fn = c.service("capacity", "sprint_capacity")
            out["active_sprint_capacity"] = _plain(c.call_adaptive(fn, db=db, sprint=sprint, sprint_id=sprint.id))
        except NotAvailable as exc:
            out["active_sprint_capacity"] = {"error": str(exc)}
    return out


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


@tool(
    "metrics_overview",
    "Project metrics: velocity history, throughput, cycle time, WIP, scope. Use for 'how are we doing'.",
    {"project_id": {"type": "string", "required": True}},
)
def metrics_overview(db: Session, user: User | None, project_id: str) -> Any:
    proj = _project(db, project_id)
    fn = c.service("metrics", "overview")
    return _plain(c.call_adaptive(fn, db=db, project=proj, project_id=proj.id))


@tool(
    "evm_report",
    "Earned-value report (PV, EV, AC, SPI, CPI, EAC, forecasts) for a project with EVM enabled.",
    {"project_id": {"type": "string", "required": True}},
)
def evm_report(db: Session, user: User | None, project_id: str) -> Any:
    proj = _project(db, project_id)
    fn = c.service("evm", "report")
    return _plain(c.call_adaptive(fn, db=db, project=proj, project_id=proj.id))


@tool(
    "forecast",
    "Monte Carlo forecast over weekly throughput. mode='how_many' answers 'how much can we finish in N weeks'; "
    "mode='when' answers 'when will N items be done'.",
    {
        "project_id": {"type": "string", "required": True},
        "mode": {"type": "string", "enum": ["how_many", "when"], "required": True},
        "weeks": {"type": "integer", "description": "for how_many"},
        "items": {"type": "integer", "description": "for when"},
    },
)
def forecast(
    db: Session, user: User | None, project_id: str, mode: str, weeks: int | None = None, items: int | None = None
) -> Any:
    proj = _project(db, project_id)
    fn = c.service("forecast", "monte_carlo")
    return _plain(
        c.call_adaptive(
            fn, db=db, project=proj, project_id=proj.id, mode=mode, weeks=weeks or 2, items=items or 20, sims=2000
        )
    )


# ---------------------------------------------------------------------------
# Personal / intake / slack
# ---------------------------------------------------------------------------


@tool(
    "create_action_item",
    "Create a PRIVATE action item (to-do) for the current user only. Nobody else can see it.",
    {
        "title": {"type": "string", "required": True},
        "notes": {"type": "string"},
        "due_date": {"type": "string", "description": "YYYY-MM-DD"},
        "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "work_item_id": {"type": "string", "description": "related item id or key"},
    },
    mutating=True,
)
def create_action_item(
    db: Session,
    user: User | None,
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
    priority: str | None = None,
    work_item_id: str | None = None,
) -> dict:
    if user is None:
        raise ValueError("No current user; action items are private and need a signed-in user.")
    wi = _item(db, work_item_id) if work_item_id else None
    payload = {
        "title": title,
        "notes": notes,
        "due_date": due_date,
        "priority": priority or "medium",
        "work_item_id": wi.id if wi else None,
        "project_id": wi.project_id if wi else None,
        "source": "agent",
    }
    try:
        fn = c.service("action_items", "create_action_item")
        ai = c.call_adaptive(fn, db=db, user=user, owner=user, owner_id=user.id, data=payload, payload=payload, **payload)
    except NotAvailable:
        due = None
        if due_date:
            try:
                due = date.fromisoformat(due_date[:10])
            except ValueError:
                due = None
        ai = ActionItem(owner_id=user.id, **{**payload, "due_date": due})
        db.add(ai)
        db.flush()
        bus.emit("action_item.created", entity_type="action_item", entity_id=ai.id, actor_id=user.id)
    return {"id": getattr(ai, "id", None), "title": title, "summary": f"action item created: {title}"}


@tool("list_my_action_items", "List the current user's open private action items.", {})
def list_my_action_items(db: Session, user: User | None) -> list[dict]:
    if user is None:
        return []
    try:
        fn = c.service("action_items", "list_action_items")
        rows = c.call_adaptive(fn, db=db, user=user, owner=user, owner_id=user.id, include_done=False)
    except NotAvailable:
        rows = db.scalars(
            select(ActionItem)
            .where(ActionItem.owner_id == user.id, ActionItem.done.is_(False))
            .order_by(ActionItem.position, ActionItem.due_date)
        ).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "priority": a.priority,
            "work_item_id": a.work_item_id,
        }
        for a in rows
    ]


@tool(
    "create_intake_request",
    "Log a new intake request (a stakeholder ask) so the intake agent can clarify and turn it into backlog.",
    {
        "subject": {"type": "string", "required": True},
        "body": {"type": "string", "required": True},
        "project_id": {"type": "string"},
    },
    mutating=True,
)
def create_intake_request(
    db: Session, user: User | None, subject: str, body: str, project_id: str | None = None
) -> dict:
    proj = c.resolve_project(db, project_id) if project_id else None
    req = IntakeRequest(
        subject=subject[:300],
        original_body=body,
        channel="chat",
        requester_name=user.name if user else None,
        requester_email=user.email if user else None,
        project_id=proj.id if proj else None,
        owner_id=user.id if user else None,
    )
    db.add(req)
    db.flush()
    bus.emit("intake.created", project_id=req.project_id, entity_type="intake", entity_id=req.id)
    return {"id": req.id, "state": req.state, "summary": f"intake request logged: {subject}"}


@tool(
    "send_slack_message",
    "Post a message to Slack. ONLY use this when the user explicitly asks you to post/send something to Slack; "
    "never post proactively. Omit channel to use the project's or workspace default channel.",
    {"channel": {"type": "string"}, "text": {"type": "string", "required": True}},
    mutating=True,
)
def send_slack_message(db: Session, user: User | None, text: str, channel: str | None = None) -> dict:
    fn = c.integration("slack", "post_message")
    channel = channel or get_settings().slack_default_channel
    res = c.call_adaptive(fn, channel=channel, text=text, body=text)
    return {"ok": True, "channel": channel, "result": _plain(res), "summary": f"posted to {channel or 'default'}"}


# ---------------------------------------------------------------------------
# tiny helpers used elsewhere
# ---------------------------------------------------------------------------


def count_items(db: Session, project_id: str) -> int:
    return db.scalar(select(func.count(WorkItem.id)).where(WorkItem.project_id == project_id)) or 0
