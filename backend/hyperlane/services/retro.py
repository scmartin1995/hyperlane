"""Sprint retrospectives: columns of entries, votes, mood, a summary and action items on close."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import ActionItem, Project, Retro, Sprint, SprintCommitment, StatusTransition, User, WorkItem
from . import metrics
from .events import bus

log = logging.getLogger(__name__)

COLUMNS = ("went_well", "improve", "kudos", "actions")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _emit(retro: Retro, actor: User | None = None, **data: Any) -> None:
    bus.emit(
        "retro.updated",
        project_id=retro.project_id,
        entity_type="retro",
        entity_id=retro.id,
        actor_id=actor.id if actor else None,
        data={"sprint_id": retro.sprint_id, **data},
    )


def to_dict(retro: Retro) -> dict[str, Any]:
    return {
        "id": retro.id,
        "sprint_id": retro.sprint_id,
        "project_id": retro.project_id,
        "state": retro.state,
        "went_well": list(retro.went_well or []),
        "improve": list(retro.improve or []),
        "kudos": list(retro.kudos or []),
        "actions": list(retro.actions or []),
        "mood": dict(retro.mood or {}),
        "agent_summary": retro.agent_summary,
        "stats": dict(retro.stats or {}),
        "facilitator_id": retro.facilitator_id,
    }


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def stats(db: Session, sprint: Sprint) -> dict[str, Any]:
    """Freeze the sprint's numbers (velocity vs commitment, carry-over, cycle time, blocked, mood)."""
    project = sprint.project or db.get(Project, sprint.project_id)
    mode = metrics.estimation(project)
    done = metrics.done_statuses(project)
    commits = list(db.scalars(select(SprintCommitment).where(SprintCommitment.sprint_id == sprint.id)))
    if commits:
        ids = {c.work_item_id for c in commits if c.removed_at is None}
        items = list(db.scalars(select(WorkItem).where(WorkItem.id.in_(ids)))) if ids else []
        added_mid = sum(1 for c in commits if c.added_mid_sprint)
    else:
        items = list(db.scalars(select(WorkItem).where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False))))
        added_mid = 0
    done_items = [i for i in items if i.status in done]
    committed = sprint.committed_points if mode == "points" and sprint.committed_points else sum(metrics.item_value(i, mode) for i in items)
    completed = sprint.completed_points if mode == "points" and sprint.completed_points else sum(metrics.item_value(i, mode) for i in done_items)
    if mode == "throughput":
        committed = sprint.committed_count or len(items)
        completed = sprint.completed_count or len(done_items)
    carried = [i for i in items if i.status not in done]

    trs: dict[str, list[StatusTransition]] = {}
    if done_items:
        for t in db.scalars(
            select(StatusTransition)
            .where(StatusTransition.work_item_id.in_([i.id for i in done_items]))
            .order_by(StatusTransition.at)
        ):
            trs.setdefault(t.work_item_id, []).append(t)
    cycles = []
    for i in done_items:
        if not i.completed_at:
            continue
        start = next((t.at for t in trs.get(i.id, []) if t.to_category == "in_progress"), None) or i.started_at or i.created_at
        cycles.append(max(0.0, (i.completed_at - start).total_seconds() / 86400.0))
    blocked = sum(1 for i in items if i.blocked and i.status not in done)
    return {
        "sprint_name": sprint.name,
        "estimation": mode,
        "committed": round(float(committed), 2),
        "completed": round(float(completed), 2),
        "completion_pct": round(float(completed) / float(committed) * 100, 1) if committed else 0.0,
        "items_total": len(items),
        "items_done": len(done_items),
        "carried_over": len(carried),
        "carried_over_keys": [f"{project.key}-{i.number}" for i in carried][:20],
        "added_mid_sprint": added_mid,
        "avg_cycle_days": round(sum(cycles) / len(cycles), 2) if cycles else 0.0,
        "blocked": blocked,
        "start_date": sprint.start_date.isoformat(),
        "end_date": sprint.end_date.isoformat(),
        "closed_at": sprint.closed_at.isoformat() if sprint.closed_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def get_or_create(db: Session, sprint: Sprint, actor: User | None = None) -> Retro:
    retro = db.scalar(select(Retro).where(Retro.sprint_id == sprint.id))
    if retro is None:
        retro = Retro(sprint_id=sprint.id, project_id=sprint.project_id, facilitator_id=actor.id if actor else None)
        retro.stats = stats(db, sprint)
        db.add(retro)
        db.commit()
        _emit(retro, actor, created=True)
    return retro


_UPDATABLE = {"went_well", "improve", "kudos", "actions", "mood", "agent_summary", "facilitator_id", "state"}


def update(db: Session, retro: Retro, patch: dict[str, Any], actor: User | None = None) -> Retro:
    for k, v in patch.items():
        if k not in _UPDATABLE or v is None:
            continue
        if k == "state" and v not in ("open", "closed"):
            raise ValueError("state must be open or closed")
        if k in COLUMNS:
            v = [_normalize_entry(k, e) for e in v]
        setattr(retro, k, v)
    db.commit()
    _emit(retro, actor)
    return retro


def _normalize_entry(column: str, e: dict[str, Any]) -> dict[str, Any]:
    base = {"id": e.get("id") or _new_id(), "text": str(e.get("text") or "")}
    if column == "actions":
        base.update({"owner_id": e.get("owner_id"), "done": bool(e.get("done", False)), "action_item_id": e.get("action_item_id")})
    else:
        base.update({"author_id": e.get("author_id"), "votes": int(e.get("votes") or 0)})
    return base


def add_item(
    db: Session, retro: Retro, column: str, text: str, actor: User | None = None, owner_id: str | None = None
) -> Retro:
    if column not in COLUMNS:
        raise ValueError(f"column must be one of {', '.join(COLUMNS)}")
    if retro.state == "closed":
        raise ValueError("Retro is closed")
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if column == "actions":
        entry = {"id": _new_id(), "text": text, "owner_id": owner_id or (actor.id if actor else None), "done": False, "action_item_id": None}
    else:
        entry = {"id": _new_id(), "text": text, "author_id": actor.id if actor else None, "votes": 0}
    setattr(retro, column, [*(getattr(retro, column) or []), entry])
    db.commit()
    _emit(retro, actor, column=column, entry_id=entry["id"])
    return retro


def vote(db: Session, retro: Retro, column: str, entry_id: str, actor: User | None = None) -> Retro:
    if column not in COLUMNS or column == "actions":
        raise ValueError("Can only vote on went_well, improve or kudos")
    entries = [dict(e) for e in (getattr(retro, column) or [])]
    hit = next((e for e in entries if e.get("id") == entry_id), None)
    if hit is None:
        raise ValueError("Entry not found")
    hit["votes"] = int(hit.get("votes") or 0) + 1
    setattr(retro, column, entries)
    db.commit()
    _emit(retro, actor, column=column, entry_id=entry_id, votes=hit["votes"])
    return retro


def mood(db: Session, retro: Retro, user: User, score: int) -> Retro:
    score = int(score)
    if not 1 <= score <= 5:
        raise ValueError("score must be 1..5")
    retro.mood = {**(retro.mood or {}), user.id: score}
    db.commit()
    _emit(retro, user, mood=True)
    return retro


# ---------------------------------------------------------------------------
# summary + close
# ---------------------------------------------------------------------------


def _heuristic_summary(retro: Retro, s: dict[str, Any]) -> str:
    parts: list[str] = []
    unit = "items" if s.get("estimation") == "throughput" else ("hours" if s.get("estimation") == "hours" else "points")
    committed, completed = s.get("committed", 0), s.get("completed", 0)
    if committed:
        pct = s.get("completion_pct", 0)
        verdict = "a strong sprint" if pct >= 90 else ("a decent sprint" if pct >= 70 else "a tough sprint")
        parts.append(f"{s.get('sprint_name', 'The sprint')} delivered {completed:g} of {committed:g} committed {unit} ({pct:.0f}%), {verdict}.")
    else:
        parts.append(f"{s.get('sprint_name', 'The sprint')} finished with {s.get('items_done', 0)} items done.")
    if s.get("carried_over"):
        parts.append(f"{s['carried_over']} item{'s' if s['carried_over'] != 1 else ''} carried over")
        if s.get("added_mid_sprint"):
            parts[-1] += f" and {s['added_mid_sprint']} added mid-sprint, which suggests scope churn"
        parts[-1] += "."
    if s.get("avg_cycle_days"):
        parts.append(f"Average cycle time was {s['avg_cycle_days']:.1f} days.")
    if s.get("blocked"):
        parts.append(f"{s['blocked']} item{'s' if s['blocked'] != 1 else ''} ended the sprint blocked.")
    moods = [int(v) for v in (retro.mood or {}).values()]
    if moods:
        avg = sum(moods) / len(moods)
        feel = "upbeat" if avg >= 4 else ("okay" if avg >= 3 else "low")
        parts.append(f"Team mood averaged {avg:.1f}/5 ({feel}).")
    top: list[str] = []
    for col, label in (("went_well", "went well"), ("improve", "to improve")):
        entries = sorted(retro.__getattribute__(col) or [], key=lambda e: -int(e.get("votes") or 0))
        if entries:
            top.append(f"Top {label}: \"{entries[0]['text']}\"")
    if top:
        parts.append(" ".join(top) + ".")
    if retro.actions:
        parts.append(f"{len(retro.actions)} action{'s' if len(retro.actions) != 1 else ''} agreed.")
    return " ".join(parts)


def generate_summary(db: Session, retro: Retro, actor: User | None = None) -> Retro:
    sprint = db.get(Sprint, retro.sprint_id)
    s = stats(db, sprint) if sprint else dict(retro.stats or {})
    retro.stats = s
    summary: str | None = None
    try:
        from ..agent import summarize_retro  # type: ignore
    except ImportError:
        summarize_retro = None
    if summarize_retro is not None:
        try:
            summary = summarize_retro(retro, s)
        except Exception:
            log.info("agent retro summary unavailable; using heuristic", exc_info=True)
    retro.agent_summary = (summary or "").strip() or _heuristic_summary(retro, s)
    db.commit()
    _emit(retro, actor, summary=True)
    return retro


def _create_action_item(db: Session, owner: User, title: str, retro: Retro, sprint: Sprint | None) -> ActionItem | None:
    data = {
        "title": title,
        "notes": f"From the retro of {sprint.name}" if sprint else "From a sprint retro",
        "project_id": retro.project_id,
        "source": "retro",
        "source_ref": retro.id,
        "priority": "medium",
    }
    try:
        from .action_items import create_action_item  # type: ignore

        try:
            created = create_action_item(db, owner, data)
            if created is not None:
                return created
        except Exception:
            log.debug("services.action_items.create_action_item failed; using ORM", exc_info=True)
            db.rollback()
    except ImportError:
        pass
    ai = ActionItem(owner_id=owner.id, **data)
    db.add(ai)
    db.flush()
    bus.emit("action_item.created", entity_type="action_item", entity_id=ai.id, actor_id=owner.id, project_id=retro.project_id)
    return ai


def close(db: Session, retro: Retro, actor: User | None = None) -> Retro:
    sprint = db.get(Sprint, retro.sprint_id)
    actions = [dict(a) for a in (retro.actions or [])]
    created = 0
    for a in actions:
        if a.get("action_item_id") or not a.get("owner_id") or not a.get("text"):
            continue
        owner = db.get(User, a["owner_id"])
        if owner is None:
            continue
        ai = _create_action_item(db, owner, a["text"], retro, sprint)
        if ai is not None:
            a["action_item_id"] = ai.id
            created += 1
    retro.actions = actions
    retro.state = "closed"
    if sprint is not None:
        retro.stats = {**stats(db, sprint), "closed_retro_at": utcnow().isoformat()}
    db.commit()
    _emit(retro, actor, closed=True, action_items_created=created)
    return retro
