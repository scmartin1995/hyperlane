"""Intake clarification agent: understand a stakeholder request, ask the few questions that matter, get it ready."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import session_scope, utcnow
from ..models import IntakeMessage, IntakeRequest, Project, User, WorkItem
from . import _compat as c
from .prompts import INTAKE_SYSTEM, project_context
from .provider import ProviderError, get_provider

log = logging.getLogger(__name__)

READY_CONFIDENCE = 0.75
AGENT_AUTHOR = "Hyperlane Agent"


class ProposedItem(BaseModel):
    type: str = "story"
    title: str
    description: str = ""
    points: float | None = None
    acceptance_criteria: str | None = None


class IntakeAnalysis(BaseModel):
    problem: str = ""
    outcome: str = ""
    users: str = ""
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low", "none"] = "medium"
    urgency: str = "normal"
    open_questions: list[str] = Field(default_factory=list, description="most valuable first, max 3")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    out_of_scope: bool = False
    proposed_items: list[ProposedItem] = Field(default_factory=list)
    summary: str = Field("", description="2-3 sentences: what they want and why, in plain words")


def _transcript(req: IntakeRequest) -> tuple[str, int]:
    lines = [f"[requester] {req.original_body.strip()}"]
    replies = 0
    for m in req.messages:
        if m.direction == "inbound":
            replies += 1
            lines.append(f"[requester] {m.body.strip()}")
        elif m.direction == "outbound":
            lines.append(f"[agent] {m.body.strip()}")
        else:
            lines.append(f"[team note] {m.body.strip()}")
    return "\n\n".join(lines), replies


def _analysis_prompt(db: Session, req: IntakeRequest) -> str:
    transcript, replies = _transcript(req)
    project = db.get(Project, req.project_id) if req.project_id else None
    parts = [
        f"Subject: {req.subject}",
        f"Requester: {req.requester_name or 'unknown'} <{req.requester_email or 'no email'}> via {req.channel}",
        f"Replies from requester: {replies}",
        f"Questions already asked by the agent: {req.questions_asked} of {req.max_questions}",
    ]
    if project:
        parts.append("Target project:\n" + project_context(db, project))
        parts.append("Use the project's item types for proposed_items; leaf items get points on the project's scale.")
    else:
        parts.append("No target project yet; use generic types (epic/feature/story) for proposed_items.")
    parts.append("Conversation so far:\n" + transcript)
    parts.append(
        "Analyse the request. If you'd need answers before the team could build this, put the 1-3 most "
        "valuable questions in open_questions (most valuable first) and keep confidence honest."
    )
    return "\n\n".join(parts)


def _clarifying_message(req: IntakeRequest, analysis: dict[str, Any]) -> str:
    questions = [q.strip() for q in analysis.get("open_questions") or [] if q.strip()][:3]
    if not questions:
        questions = ["What would a great outcome look like for you?", "Who will use this, and how often?"]
    name = (req.requester_name or "there").split()[0]
    understood = analysis.get("summary") or analysis.get("problem") or ""
    lines = [f"Hi {name},", ""]
    lines.append(f"Thanks for sending this over. Here's what I understood: {understood}".rstrip(": ") + "")
    lines.append("")
    lines.append("A couple of quick questions so we scope it right:")
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("Reply to this message and I'll take it from there.")
    lines.append("")
    lines.append("- Hyperlane")
    return "\n".join(lines)


def _looks_abusive(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in ("fuck you", "idiot", "stupid team", "kill yourself"))


async def analyze(request_id: str) -> IntakeRequest:
    """Analyse a request; ask ONE clarifying message or mark it ready. Returns the refreshed request."""
    provider = get_provider()
    with session_scope() as db:
        req = db.get(IntakeRequest, request_id)
        if req is None:
            raise ValueError("Intake request not found")
        if req.state in ("converted", "rejected"):
            return req
        _mirror(db, req, create_only=True)
        prompt = _analysis_prompt(db, req)

    try:
        analysis = await provider.complete(INTAKE_SYSTEM, prompt, json_schema=IntakeAnalysis)
        assert isinstance(analysis, dict)
    except ProviderError as exc:
        log.warning("intake analysis failed for %s: %s", request_id, exc)
        with session_scope() as db:
            req = db.get(IntakeRequest, request_id)
            req.needs_human = True
            req.summary = req.summary or f"Agent unavailable: {exc}"
            req.last_activity_at = utcnow()
            db.flush()
            _mirror(db, req)
            _emit(req)
            return req

    outbound_body: str | None = None
    with session_scope() as db:
        req = db.get(IntakeRequest, request_id)
        confidence = float(analysis.get("confidence") or 0.0)
        out_of_scope = bool(analysis.get("out_of_scope")) or _looks_abusive(req.original_body)
        req.requirements = {k: v for k, v in analysis.items() if k not in ("summary", "out_of_scope")}
        req.summary = analysis.get("summary") or analysis.get("problem") or req.summary
        req.last_activity_at = utcnow()
        if out_of_scope:
            req.needs_human = True
            req.state = "on_hold" if req.state == "new" else req.state
            db.add(
                IntakeMessage(
                    request_id=req.id,
                    direction="internal",
                    author=AGENT_AUTHOR,
                    body="This request looks out of scope (or not something the team builds). Needs a human look.",
                )
            )
        elif confidence < READY_CONFIDENCE and req.questions_asked < req.max_questions:
            outbound_body = _clarifying_message(req, analysis)
            db.add(IntakeMessage(request_id=req.id, direction="outbound", author=AGENT_AUTHOR, body=outbound_body))
            req.questions_asked += 1
            req.state = "clarifying"
        else:
            req.state = "ready"
            if confidence < READY_CONFIDENCE:
                req.needs_human = True  # out of questions and still unsure
        db.flush()
        req_id = req.id

    if outbound_body:
        _try_send_reply(req_id, outbound_body)

    with session_scope() as db:
        req = db.get(IntakeRequest, req_id)
        _ = req.messages  # load for the caller
        _mirror(db, req)
        _emit(req)
        return req


def _mirror(db: Session, req: IntakeRequest, create_only: bool = False) -> None:
    """Keep the request's backlog item in step (the backlog is the inbox)."""
    try:
        from ..services import triage

        if create_only:
            triage.ensure_work_item(db, req)
        else:
            triage.sync_work_item(db, req)
    except Exception:  # noqa: BLE001
        log.exception("could not mirror request %s into the backlog", req.id)


def _try_send_reply(request_id: str, body: str) -> None:
    try:
        send_reply = c.integration("email", "send_reply")
    except c.NotAvailable:
        return
    try:
        with session_scope() as db:
            req = db.get(IntakeRequest, request_id)
            if req.channel != "email" or not req.requester_email:
                return
            c.call_adaptive(send_reply, request=req, req=req, body=body, text=body)
    except Exception as exc:  # noqa: BLE001 - email failures are logged; the message is stored anyway
        log.warning("intake reply could not be sent for %s: %s", request_id, exc)


def _emit(req: IntakeRequest) -> None:
    from ..services.events import bus

    bus.emit(
        "intake.updated",
        project_id=req.project_id,
        entity_type="intake",
        entity_id=req.id,
        data={"state": req.state, "needs_human": req.needs_human, "questions_asked": req.questions_asked},
    )


def analyze_sync(request_id: str) -> IntakeRequest:
    """For callers without an event loop (the email poller runs in a thread)."""
    from . import _run_sync

    return _run_sync(analyze(request_id))


def convert(
    db: Session,
    request: IntakeRequest,
    project: Project,
    parent_id: str | None,
    items: list[dict[str, Any]] | None,
    user: User | None,
) -> list[WorkItem]:
    """Turn the proposed items (or the given override) into real backlog items."""
    proposed = items if items is not None else (request.requirements or {}).get("proposed_items") or []
    if not proposed:
        proposed = [
            {
                "type": c.leaf_type(project),
                "title": request.subject[:300],
                "description": request.original_body,
                "acceptance_criteria": "\n".join(f"- {a}" for a in (request.requirements or {}).get("acceptance") or []),
            }
        ]
    valid_types = {t["key"] for t in (project.item_types or [])}
    leaf = c.leaf_type(project)
    parent = c.resolve_item(db, parent_id) if parent_id else None
    specs: list[dict[str, Any]] = []
    for i, it in enumerate(proposed):
        itype = it.get("type") or leaf
        if valid_types and itype not in valid_types:
            itype = leaf
        spec: dict[str, Any] = {
            "temp_id": it.get("temp_id") or f"i{i + 1}",
            "parent_temp_id": it.get("parent_temp_id"),
            "type": itype,
            "title": it.get("title") or request.subject,
            "description": it.get("description") or "",
            "acceptance_criteria": it.get("acceptance_criteria"),
            "points": it.get("points"),
            "priority": (request.requirements or {}).get("priority") or "medium",
            "labels": it.get("labels") or [],
            "source": request.channel if request.channel in ("email", "slack", "chat") else "agent",
            "source_ref": request.id,
        }
        if parent and not spec["parent_temp_id"]:
            spec["parent_id"] = parent.id
        specs.append(spec)
    created = c.bulk_create(db, project, specs, user)
    request.converted_item_ids = [it.id for it in created]
    request.project_id = project.id
    request.state = "converted"
    request.last_activity_at = utcnow()
    db.add(
        IntakeMessage(
            request_id=request.id,
            direction="internal",
            author=user.name if user else AGENT_AUTHOR,
            body=f"Converted into {len(created)} item(s): " + ", ".join(c.item_key(it, project) for it in created),
        )
    )
    db.flush()
    return created


async def analyze_later(request_id: str, delay: float = 0.0) -> None:
    """Fire-and-forget helper for routers that don't want to block."""
    if delay:
        await asyncio.sleep(delay)
    try:
        await analyze(request_id)
    except Exception:
        log.exception("background intake analysis failed")
