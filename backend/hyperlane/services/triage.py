"""Requests become backlog items.

A request (email, form, Slack) is mirrored into a work item the moment it arrives, labelled
``needs-triage``. The assistant's clarifying thread shows up as the item's discussion and its
findings land in the item's description / acceptance criteria. Triage actions (accept, escalate,
decline, snooze) live on the item, so the backlog is the only inbox anyone needs.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Comment, IntakeMessage, IntakeRequest, Project, Sprint, User, WorkItem, Workspace
from . import items as items_svc
from .events import bus

log = logging.getLogger(__name__)

TRIAGE_LABEL = "needs-triage"
OPEN_STATES = ("new", "clarifying", "ready", "snoozed")
AGENT_AUTHOR = "Hyperlane Agent"
_KEY_RE = re.compile(r"\[([A-Z][A-Z0-9]{1,9})\]")


# ------------------------------------------------------------------ routing


def default_project(db: Session, subject: str | None = None) -> Project | None:
    """Route a request: ``[KEY]`` in the subject → workspace default → first active project."""
    if subject:
        m = _KEY_RE.search(subject)
        if m:
            proj = db.execute(select(Project).where(Project.key == m.group(1))).scalar_one_or_none()
            if proj is not None:
                return proj
    ws = db.get(Workspace, "default")
    pid = (ws.settings or {}).get("intake_project_id") if ws else None
    if pid:
        proj = db.get(Project, pid)
        if proj is not None and proj.status != "archived":
            return proj
    return db.execute(
        select(Project).where(Project.status == "active").order_by(Project.created_at)
    ).scalars().first()


def _intake_meta(req: IntakeRequest) -> dict[str, Any]:
    reqs = req.requirements or {}
    return {
        "request_id": req.id,
        "state": req.state,
        "channel": req.channel,
        "requester_name": req.requester_name,
        "requester_email": req.requester_email,
        "confidence": reqs.get("confidence"),
        "questions_asked": req.questions_asked,
        "max_questions": req.max_questions,
        "needs_human": req.needs_human,
        "summary": req.summary,
        "open_questions": reqs.get("open_questions") or [],
        "proposed_count": len(reqs.get("proposed_items") or []),
        "snoozed_until": (req.requirements or {}).get("snoozed_until"),
        "last_activity_at": req.last_activity_at.isoformat() if req.last_activity_at else None,
    }


def _description(req: IntakeRequest) -> str:
    who = req.requester_name or req.requester_email or "someone"
    if req.requester_name and req.requester_email:
        who = f"{req.requester_name} <{req.requester_email}>"
    head = f"**Request from {who}** via {req.channel}\n\n{req.original_body.strip()}"
    reqs = req.requirements or {}
    if not reqs:
        return head
    parts = [head, "\n---\n### What the assistant understood"]
    if req.summary:
        parts.append(req.summary)
    for key, title in (("problem", "Problem"), ("outcome", "Desired outcome"), ("users", "Who it's for")):
        if reqs.get(key):
            parts.append(f"**{title}:** {reqs[key]}")
    for key, title in (("scope_in", "In scope"), ("scope_out", "Out of scope"), ("constraints", "Constraints")):
        vals = reqs.get(key) or []
        if vals:
            parts.append(f"**{title}**\n" + "\n".join(f"- {v}" for v in vals))
    if reqs.get("open_questions"):
        parts.append("**Still open**\n" + "\n".join(f"- {q}" for q in reqs["open_questions"]))
    return "\n\n".join(parts)


# ------------------------------------------------------------------ mirroring


def ensure_work_item(db: Session, req: IntakeRequest) -> WorkItem | None:
    """Create the backlog item for a request if it doesn't exist yet."""
    if req.work_item_id:
        item = db.get(WorkItem, req.work_item_id)
        if item is not None:
            return item
    project = db.get(Project, req.project_id) if req.project_id else None
    if project is None:
        project = default_project(db, req.subject)
    if project is None:
        log.info("no project to route request %s into", req.id)
        return None
    req.project_id = project.id
    source = req.channel if req.channel in ("email", "slack", "chat") else "manual"
    data = {
        "title": _KEY_RE.sub("", req.subject).strip()[:300] or "(untitled request)",
        "description": _description(req),
        "labels": [TRIAGE_LABEL],
        "priority": "medium",
        "source": source,
        "source_ref": req.id,
        "custom": {"intake": _intake_meta(req)},
    }
    item = items_svc.create_item(db, project, data, None)
    req.work_item_id = item.id
    db.flush()
    _mirror_messages(db, req, item)
    return item


def _mirror_messages(db: Session, req: IntakeRequest, item: WorkItem) -> None:
    """Every message after the original request becomes a comment (idempotent)."""
    msgs = list(req.messages)
    existing = {
        c.external_ref
        for c in db.execute(select(Comment).where(Comment.work_item_id == item.id)).scalars()
        if c.external_ref and c.external_ref.startswith("intake-msg:")
    }
    for i, m in enumerate(msgs):
        ref = f"intake-msg:{m.id}"
        if ref in existing:
            continue
        if i == 0 and m.direction == "inbound":
            continue  # the original request lives in the description
        if m.direction == "internal" and m.author == AGENT_AUTHOR and not m.body.strip():
            continue
        if m.direction == "outbound":
            source, author_name = "agent", f"{AGENT_AUTHOR} → {req.requester_name or req.requester_email or 'requester'}"
        elif m.direction == "inbound":
            source, author_name = ("email" if req.channel == "email" else "web"), (req.requester_name or m.author)
        else:
            source, author_name = "web", m.author
        c = Comment(work_item_id=item.id, author_name=author_name, body=m.body, source=source, external_ref=ref)
        c.created_at = c.updated_at = m.created_at
        db.add(c)
    db.flush()


def sync_work_item(db: Session, req: IntakeRequest) -> WorkItem | None:
    """Push the request's latest state (findings, thread, priority) onto its item."""
    item = ensure_work_item(db, req)
    if item is None:
        return None
    reqs = req.requirements or {}
    item.description = _description(req)
    meta = _intake_meta(req)
    custom = dict(item.custom or {})
    prev = custom.get("intake") or {}
    if prev.get("state") in ("accepted", "declined") and req.state not in ("rejected",):
        meta["state"] = prev["state"]
    custom["intake"] = meta
    item.custom = custom
    if not item.acceptance_criteria and reqs.get("acceptance"):
        item.acceptance_criteria = "\n".join(f"- {a}" for a in reqs["acceptance"])
    prio = reqs.get("priority")
    if prio in items_svc.PRIORITIES and prev.get("state") not in ("accepted",):
        item.priority = prio
    item.updated_at = utcnow()
    _mirror_messages(db, req, item)
    db.flush()
    bus.emit("work_item.updated", project_id=item.project_id, entity_type="work_item", entity_id=item.id, data={"intake": True})
    return item


# ------------------------------------------------------------------ triage actions


def _set_state(item: WorkItem, state: str, **extra: Any) -> None:
    custom = dict(item.custom or {})
    meta = dict(custom.get("intake") or {})
    meta["state"] = state
    meta.update(extra)
    custom["intake"] = meta
    item.custom = custom


def _request_for(db: Session, item: WorkItem) -> IntakeRequest | None:
    if item.source_ref:
        req = db.get(IntakeRequest, item.source_ref)
        if req is not None:
            return req
    return db.execute(select(IntakeRequest).where(IntakeRequest.work_item_id == item.id)).scalar_one_or_none()


def _drop_label(db: Session, item: WorkItem) -> None:
    item.labels = [label for label in item.labels if label.name != TRIAGE_LABEL]


def _child_type(project: Project, parent_type: str) -> str | None:
    types = sorted(project.item_types or [], key=lambda t: t["level"])
    me = next((t for t in types if t["key"] == parent_type), None)
    if me is None:
        return None
    finer = [t for t in types if t["level"] > me["level"]]
    return finer[0]["key"] if finer else None


def accept(db: Session, item: WorkItem, user: User | None, *, type: str | None = None, create_children: bool = True) -> list[WorkItem]:
    """Keep the item in the backlog. Optionally expand the assistant's proposed items underneath it."""
    project = db.get(Project, item.project_id)
    req = _request_for(db, item)
    if type and project and any(t["key"] == type for t in project.item_types or []):
        item.type = type
    _drop_label(db, item)
    _set_state(item, "accepted", accepted_by=user.id if user else None)
    created: list[WorkItem] = []
    proposed = ((req.requirements or {}).get("proposed_items") or []) if req else []
    if create_children and proposed and project:
        child_type = _child_type(project, item.type)
        if child_type is None:
            # leaf-level item: adopt the first proposal's detail instead of nesting
            first = proposed[0]
            if first.get("acceptance_criteria") and not item.acceptance_criteria:
                item.acceptance_criteria = first["acceptance_criteria"]
            if first.get("points") and item.points is None:
                item.points = first["points"]
        else:
            valid = {t["key"] for t in project.item_types or []}
            specs = []
            for i, p in enumerate(proposed):
                t = p.get("type") if p.get("type") in valid else child_type
                specs.append({
                    "temp_id": f"p{i}", "type": t, "parent_id": item.id, "title": p.get("title") or item.title,
                    "description": p.get("description") or "", "acceptance_criteria": p.get("acceptance_criteria"),
                    "points": p.get("points"), "priority": item.priority, "labels": p.get("labels") or [],
                    "source": item.source, "source_ref": item.source_ref,
                })
            created = items_svc.bulk_create(db, project, specs, user)
    if req is not None:
        req.state = "converted"
        req.converted_item_ids = [item.id] + [c.id for c in created]
        req.last_activity_at = utcnow()
        db.add(IntakeMessage(request_id=req.id, direction="internal", author=user.name if user else AGENT_AUTHOR,
                             body=f"Accepted into the backlog as {items_svc.item_key(item)}" + (f" with {len(created)} child item(s)" if created else "")))
    db.flush()
    _emit(db, item, "accepted", user)
    return created


def escalate(db: Session, item: WorkItem, user: User | None, *, sprint_id: str | None = None, type: str | None = None) -> list[WorkItem]:
    """Accept and pull straight into the active (or given) sprint."""
    created = accept(db, item, user, type=type, create_children=True)
    sprint = db.get(Sprint, sprint_id) if sprint_id else db.execute(
        select(Sprint).where(Sprint.project_id == item.project_id, Sprint.state == "active")
    ).scalar_one_or_none()
    if sprint is None:
        raise ValueError("No active sprint to escalate into")
    targets = created or [item]
    for t in targets:
        items_svc.move_item(db, t, sprint_id=sprint.id, actor=user)
    _set_state(item, "accepted", escalated_to=sprint.id)
    db.flush()
    return created


def decline(db: Session, item: WorkItem, user: User | None, reason: str | None = None) -> None:
    req = _request_for(db, item)
    _drop_label(db, item)
    _set_state(item, "declined", reason=reason)
    if req is not None:
        req.state = "rejected"
        req.last_activity_at = utcnow()
        db.add(IntakeMessage(request_id=req.id, direction="internal", author=user.name if user else AGENT_AUTHOR, body=f"Declined. {reason or ''}".strip()))
    db.flush()
    _emit(db, item, "declined", user)
    items_svc.archive_item(db, item, user)


def snooze(db: Session, item: WorkItem, user: User | None, until: date) -> None:
    req = _request_for(db, item)
    _set_state(item, "snoozed", snoozed_until=until.isoformat())
    if req is not None:
        req.state = "on_hold"
        reqs = dict(req.requirements or {})
        reqs["snoozed_until"] = until.isoformat()
        req.requirements = reqs
    db.flush()
    _emit(db, item, "snoozed", user)


def unsnooze_due(db: Session) -> int:
    """Scheduler helper: wake snoozed items whose date has passed."""
    today = date.today().isoformat()
    n = 0
    for item in db.execute(select(WorkItem).where(WorkItem.source_ref.is_not(None), WorkItem.is_archived.is_(False))).scalars():
        meta = (item.custom or {}).get("intake") or {}
        if meta.get("state") == "snoozed" and (meta.get("snoozed_until") or "9999") <= today:
            _set_state(item, "ready", snoozed_until=None)
            n += 1
    db.flush()
    return n


def message_requester(db: Session, item: WorkItem, body: str, user: User | None) -> IntakeMessage:
    """A human asks the requester something; goes out by email when the connector is configured."""
    req = _request_for(db, item)
    if req is None:
        raise ValueError("This item did not come from a request")
    msg = IntakeMessage(request_id=req.id, direction="outbound", author=user.name if user else AGENT_AUTHOR, body=body)
    db.add(msg)
    req.last_activity_at = utcnow()
    req.state = "clarifying" if req.state in ("new", "ready", "clarifying") else req.state
    db.flush()
    _mirror_messages(db, req, item)
    if req.channel == "email":
        try:
            from ..integrations.email import send_reply

            send_reply(req, body)
        except Exception:  # noqa: BLE001
            log.exception("could not send requester message by email")
    return msg


def _emit(db: Session, item: WorkItem, action: str, user: User | None) -> None:
    bus.emit("work_item.updated", project_id=item.project_id, entity_type="work_item", entity_id=item.id,
             actor_id=user.id if user else None, data={"triage": action})


# ------------------------------------------------------------------ listing


def list_triage(db: Session, project_id: str, include_snoozed: bool = True) -> list[dict[str, Any]]:
    rows = db.execute(
        select(WorkItem, IntakeRequest)
        .join(IntakeRequest, IntakeRequest.work_item_id == WorkItem.id)
        .where(WorkItem.project_id == project_id, WorkItem.is_archived.is_(False))
        .order_by(IntakeRequest.last_activity_at.desc())
    ).all()
    out = []
    for item, req in rows:
        meta = (item.custom or {}).get("intake") or {}
        state = meta.get("state") or req.state
        if state not in OPEN_STATES:
            continue
        if state == "snoozed" and not include_snoozed:
            continue
        d = items_svc.serialize_item(item, db).model_dump(mode="json")
        d["intake"] = {**_intake_meta(req), "state": state, "proposed_items": (req.requirements or {}).get("proposed_items") or [],
                       "requirements": req.requirements or {}}
        out.append(d)
    return out


def _wake_job() -> None:
    from ..db import session_scope

    with session_scope() as db:
        unsnooze_due(db)


try:
    from .scheduler import register_job

    register_job(_wake_job, trigger="cron", hour=6, minute=5, id="triage-unsnooze")
except Exception:  # noqa: BLE001  pragma: no cover
    pass
