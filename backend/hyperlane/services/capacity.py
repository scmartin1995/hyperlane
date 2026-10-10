"""Capacity: learn per-person delivery profiles at sprint close, size the next sprint, suggest a plan.

Availability: available_hours = (hours_per_week x sprint_weeks - days_off x hours_per_day) x focus_factor.
Suggested load per person = learned average scaled by availability (profile), else the team average,
else `available_hours x DEFAULT_POINTS_PER_HOUR`.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import CapacityEntry, CapacityProfile, Project, Sprint, SprintCommitment, User, WorkItem
from ..schemas.common import SprintOut, UserBrief, WorkItemOut
from . import metrics
from .events import bus

log = logging.getLogger(__name__)

ALPHA = 0.4  # exponential weight of the newest sprint
DEFAULT_POINTS_PER_HOUR = 0.25
PRIORITY_WEIGHT = {"critical": 40.0, "high": 30.0, "medium": 20.0, "low": 10.0, "none": 5.0}
LOW_CONFIDENCE = 0.5


# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------


def profile_to_dict(p: CapacityProfile, user: User | None = None) -> dict[str, Any]:
    out = {
        "id": p.id,
        "project_id": p.project_id,
        "user_id": p.user_id,
        "sprints_observed": p.sprints_observed,
        "avg_points": round(p.avg_points, 2),
        "avg_count": round(p.avg_count, 2),
        "points_per_hour": round(p.points_per_hour, 3),
        "commitment_accuracy": round(p.commitment_accuracy, 3),
        "stddev_points": round(p.stddev_points, 2),
        "history": list(p.history or []),
        "confidence": round(p.confidence, 2),
        "insights": list(p.insights or []),
    }
    if user is not None:
        out["user"] = UserBrief.model_validate(user).model_dump()
    return out


def item_to_dict(item: WorkItem, db: Session) -> dict[str, Any]:
    """WorkItem JSON; prefers backend-core's serializer when it exists."""
    try:
        from .items import serialize_item  # type: ignore
    except ImportError:
        serialize_item = None
    if serialize_item is not None:
        try:
            out = serialize_item(item, db)
            return out.model_dump(mode="json") if hasattr(out, "model_dump") else dict(out)
        except Exception:
            log.debug("services.items.serialize_item failed; using fallback", exc_info=True)
    out = WorkItemOut.model_validate(item)
    project = item.project or db.get(Project, item.project_id)
    out.key = f"{project.key}-{item.number}" if project else str(item.number)
    out.child_count = sum(1 for c in item.children if not c.is_archived)
    out.comment_count = len(item.comments)
    return out.model_dump(mode="json")


# ---------------------------------------------------------------------------
# learning
# ---------------------------------------------------------------------------


def _ewma(old: float, new: float, n_before: int) -> float:
    return new if n_before == 0 else ALPHA * new + (1 - ALPHA) * old


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _insights(p: CapacityProfile) -> list[str]:
    out: list[str] = []
    n = p.sprints_observed
    if n <= 1:
        return [f"Only {n} sprint observed yet"]
    acc = p.commitment_accuracy
    if acc and acc < 0.85:
        out.append(f"Tends to over-commit by ~{round((1 - acc) * 100 / 5) * 5:.0f}%")
    elif acc > 1.15:
        out.append(f"Tends to under-commit by ~{round((acc - 1) * 100 / 5) * 5:.0f}%")
    else:
        out.append("Commits accurately")
    if p.avg_points > 0:
        cv = p.stddev_points / p.avg_points
        if cv < 0.2:
            out.append("Delivery is very consistent")
        elif cv > 0.5:
            out.append("Delivery varies a lot sprint to sprint")
    if n < 3:
        out.append(f"Only {n} sprints observed yet")
    try:
        from ..agent import draft_capacity_insight  # type: ignore
    except ImportError:
        return out
    try:
        extra = draft_capacity_insight(p)
    except Exception:
        log.debug("agent capacity insight unavailable", exc_info=True)
        extra = None
    if extra:
        out.extend(str(x) for x in extra[:2])
    return out


def learn_from_sprint(db: Session, sprint: Sprint) -> list[CapacityProfile]:
    """Fold a closed sprint's CapacityEntry rows into each person's CapacityProfile."""
    entries = list(db.scalars(select(CapacityEntry).where(CapacityEntry.sprint_id == sprint.id)))
    profiles: list[CapacityProfile] = []
    for e in entries:
        p = db.scalar(
            select(CapacityProfile).where(
                CapacityProfile.project_id == sprint.project_id, CapacityProfile.user_id == e.user_id
            )
        )
        if p is None:
            p = CapacityProfile(project_id=sprint.project_id, user_id=e.user_id)
            db.add(p)
        history = [h for h in (p.history or []) if h.get("sprint_id") != sprint.id]
        n = len(history)
        completed_pts = float(e.completed_points or 0.0)
        completed_cnt = float(e.completed_count or 0)
        hours = float(e.available_hours or 0.0)
        planned_pts = float(e.planned_points or 0.0)

        p.avg_points = _ewma(p.avg_points, completed_pts, n)
        p.avg_count = _ewma(p.avg_count, completed_cnt, n)
        if hours > 0:
            p.points_per_hour = _ewma(p.points_per_hour, completed_pts / hours, n)
        if planned_pts > 0:
            p.commitment_accuracy = _ewma(p.commitment_accuracy, completed_pts / planned_pts, n)
        history.append(
            {
                "sprint_id": sprint.id,
                "sprint_name": sprint.name,
                "planned": planned_pts,
                "completed": completed_pts,
                "hours": hours,
                "count": int(completed_cnt),
            }
        )
        p.history = history
        p.sprints_observed = len(history)
        p.stddev_points = _stddev([float(h.get("completed") or 0.0) for h in history])
        p.confidence = min(1.0, p.sprints_observed / 5.0)
        p.insights = _insights(p)
        profiles.append(p)
    db.commit()
    for p in profiles:
        bus.emit(
            "capacity.updated",
            project_id=sprint.project_id,
            entity_type="capacity_profile",
            entity_id=p.id,
            data={"user_id": p.user_id, "sprint_id": sprint.id},
        )
    return profiles


# ---------------------------------------------------------------------------
# sprint capacity
# ---------------------------------------------------------------------------


def _sprint_weeks(sprint: Sprint) -> float:
    return max(1, (sprint.end_date - sprint.start_date).days + 1) / 7.0


def _hours_per_day(user: User, project: Project) -> float:
    n = len((project.settings or {}).get("working_days") or [0, 1, 2, 3, 4]) or 5
    return float(user.hours_per_week or 40.0) / n


def compute_available_hours(user: User, sprint: Sprint, project: Project, days_off: float) -> float:
    weeks = _sprint_weeks(sprint)
    gross = float(user.hours_per_week or 40.0) * weeks - float(days_off or 0.0) * _hours_per_day(user, project)
    return round(max(0.0, gross) * float(user.focus_factor or 0.7), 1)


def _full_hours(user: User, sprint: Sprint) -> float:
    return float(user.hours_per_week or 40.0) * _sprint_weeks(sprint) * float(user.focus_factor or 0.7)


def members(db: Session, project: Project) -> list[User]:
    """Active users touching the project (assigned to an item or with a profile); else all active users."""
    ids: set[str] = set()
    for (uid,) in db.execute(
        select(WorkItem.assignee_id).where(
            WorkItem.project_id == project.id, WorkItem.assignee_id.is_not(None), WorkItem.is_archived.is_(False)
        ).distinct()
    ):
        ids.add(uid)
    for (uid,) in db.execute(select(CapacityProfile.user_id).where(CapacityProfile.project_id == project.id)):
        ids.add(uid)
    if project.lead_id:
        ids.add(project.lead_id)
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)))
    picked = [u for u in users if u.id in ids] if ids else users
    return picked or users


def _suggest(
    method: str, profile: CapacityProfile | None, available: float, full: float, team_avg: float | None
) -> float:
    ratio = available / full if full > 0 else 0.0
    if method == "hours":
        return round(available, 1)
    if profile is not None and profile.sprints_observed > 0:
        base = profile.avg_count if method == "throughput" else profile.avg_points
        return round(base * ratio, 1)
    if team_avg:
        return round(team_avg * ratio, 1)
    pts = available * DEFAULT_POINTS_PER_HOUR
    return round(max(1.0, pts / 3.0) if method == "throughput" else pts, 1)


def sprint_capacity(db: Session, sprint: Sprint) -> dict[str, Any]:
    project = sprint.project or db.get(Project, sprint.project_id)
    method = metrics.estimation(project)
    users = members(db, project)
    entry_users = {
        e.user_id: e for e in db.scalars(select(CapacityEntry).where(CapacityEntry.sprint_id == sprint.id))
    }
    for uid in entry_users:
        if all(u.id != uid for u in users):
            u = db.get(User, uid)
            if u is not None and u.is_active:
                users.append(u)
    profiles = {
        p.user_id: p for p in db.scalars(select(CapacityProfile).where(CapacityProfile.project_id == project.id))
    }
    observed = [p for p in profiles.values() if p.sprints_observed > 0]
    team_avg = None
    if observed:
        key = "avg_count" if method == "throughput" else "avg_points"
        team_avg = sum(getattr(p, key) for p in observed) / len(observed)

    entries = []
    dirty = False
    for u in users:
        e = entry_users.get(u.id)
        if e is None:
            e = CapacityEntry(sprint_id=sprint.id, user_id=u.id, days_off=0.0)
            e.available_hours = compute_available_hours(u, sprint, project, 0.0)
            db.add(e)
            dirty = True
        elif not e.available_hours:
            e.available_hours = compute_available_hours(u, sprint, project, e.days_off or 0.0)
            dirty = True
        p = profiles.get(u.id)
        suggested = _suggest(method, p, float(e.available_hours or 0.0), _full_hours(u, sprint), team_avg)
        entries.append((e, u, p, suggested))
    if dirty:
        db.commit()

    rows = []
    for e, u, p, suggested in entries:
        rows.append(
            {
                "id": e.id,
                "sprint_id": e.sprint_id,
                "user_id": e.user_id,
                "days_off": float(e.days_off or 0.0),
                "available_hours": float(e.available_hours or 0.0),
                "planned_points": float(e.planned_points or 0.0),
                "planned_count": int(e.planned_count or 0),
                "completed_points": float(e.completed_points or 0.0),
                "completed_count": int(e.completed_count or 0),
                "notes": e.notes,
                "user": UserBrief.model_validate(u).model_dump(),
                "suggested_points": suggested,
                "profile": profile_to_dict(p) if p is not None else None,
            }
        )
    return {
        "sprint": SprintOut.model_validate(sprint).model_dump(mode="json"),
        "entries": rows,
        "team_points": round(sum(r["suggested_points"] for r in rows), 1),
        "team_hours": round(sum(r["available_hours"] for r in rows), 1),
        "team_count": len(rows),
        "method": method,
    }


def upsert_entries(db: Session, sprint: Sprint, entries: list[dict[str, Any]]) -> dict[str, Any]:
    project = sprint.project or db.get(Project, sprint.project_id)
    for data in entries:
        uid = data.get("user_id")
        user = db.get(User, uid) if uid else None
        if user is None:
            raise ValueError(f"Unknown user {uid}")
        e = db.scalar(select(CapacityEntry).where(CapacityEntry.sprint_id == sprint.id, CapacityEntry.user_id == uid))
        if e is None:
            e = CapacityEntry(sprint_id=sprint.id, user_id=uid)
            db.add(e)
        e.days_off = float(data.get("days_off") or 0.0)
        if data.get("available_hours") is not None:
            e.available_hours = float(data["available_hours"])
        else:
            e.available_hours = compute_available_hours(user, sprint, project, e.days_off)
        if "notes" in data:
            e.notes = data.get("notes")
    db.commit()
    bus.emit("sprint.updated", project_id=sprint.project_id, entity_type="sprint", entity_id=sprint.id, data={"capacity": True})
    return sprint_capacity(db, sprint)


# ---------------------------------------------------------------------------
# plan suggestion
# ---------------------------------------------------------------------------


def _candidates(db: Session, project: Project) -> list[WorkItem]:
    done = metrics.done_statuses(project)
    levels = {t["key"]: int(t.get("level", 0)) for t in project.item_types or []}
    max_level = max(levels.values(), default=0)
    items = list(
        db.scalars(
            select(WorkItem).where(
                WorkItem.project_id == project.id, WorkItem.is_archived.is_(False), WorkItem.sprint_id.is_(None)
            )
        )
    )
    children: dict[str, int] = defaultdict(int)
    for i in items:
        if i.parent_id:
            children[i.parent_id] += 1
    out = []
    for i in items:
        if i.status in done:
            continue
        level = levels.get(i.type, max_level)
        is_leaf = children.get(i.id, 0) == 0
        if level == 0 and not (is_leaf and max_level == 0):
            continue
        if level < max_level and not is_leaf:
            continue
        out.append(i)
    return out


def _score(item: WorkItem, rank_index: int, total: int, now) -> tuple[float, str]:
    reasons: list[str] = []
    score = PRIORITY_WEIGHT.get(item.priority or "medium", 20.0)
    if item.priority in ("critical", "high"):
        reasons.append(f"{item.priority} priority")
    bv = float(item.business_value or 0)
    score += bv / 100.0 * 30.0
    if bv >= 60:
        reasons.append(f"high business value ({int(bv)})")
    rank_score = 20.0 * (1 - rank_index / total) if total > 1 else 20.0
    score += rank_score
    if rank_index < max(3, total // 5):
        reasons.append("top of backlog")
    age_days = max(0.0, (now - item.created_at).total_seconds() / 86400.0)
    score += min(10.0, age_days / 7.0)
    if age_days >= 21:
        reasons.append(f"waiting {int(age_days // 7)} weeks")
    if item.blocked:
        score -= 25.0
        reasons.append("blocked")
    if not reasons:
        reasons.append("next in rank order")
    return round(score, 1), ", ".join(reasons)


def suggest_plan(db: Session, sprint: Sprint) -> dict[str, Any]:
    project = sprint.project or db.get(Project, sprint.project_id)
    method = metrics.estimation(project)
    cap = sprint_capacity(db, sprint)
    now = utcnow()
    items = sorted(_candidates(db, project), key=lambda i: (i.rank, i.created_at))
    scored = []
    for idx, item in enumerate(items):
        s, reason = _score(item, idx, len(items), now)
        scored.append((s, item, reason))
    scored.sort(key=lambda t: (-t[0], t[1].rank))

    confidences = [e["profile"]["confidence"] for e in cap["entries"] if e["profile"]]
    confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    team_cap = float(cap["team_points"])
    budget = team_cap * (0.9 if confidence < LOW_CONFIDENCE else 1.0)

    remaining = {e["user_id"]: float(e["suggested_points"]) for e in cap["entries"]}
    per_person: dict[str, dict[str, Any]] = {uid: {"points": 0.0, "items": []} for uid in remaining}
    recommended: list[str] = []
    total = 0.0
    unestimated = 0
    for s, item, reason in scored:
        value = metrics.item_value(item, method)
        if method != "throughput" and value == 0:
            unestimated += 1
        if item.blocked:
            continue
        if total + value > budget + 1e-9:
            continue
        owner = item.assignee_id if item.assignee_id in remaining else None
        if owner is None and remaining:
            owner = max(remaining, key=lambda uid: remaining[uid])
            if remaining[owner] < value and per_person[owner]["items"]:
                # everyone is full; stop filling
                continue
        recommended.append(item.id)
        total += value
        if owner is not None:
            remaining[owner] -= value
            per_person[owner]["points"] = round(per_person[owner]["points"] + value, 1)
            per_person[owner]["items"].append(item.id)

    unit = "items" if method == "throughput" else ("h" if method == "hours" else "pts")
    notes = []
    if team_cap > 0:
        notes.append(f"Team capacity {team_cap:g} {unit}, recommending {total:g} ({total / team_cap * 100:.0f}%)")
    else:
        notes.append("No capacity known yet; add people or capacity entries")
    if confidence < LOW_CONFIDENCE:
        notes.append("Low confidence in profiles, planning to 90% of capacity")
    for e in cap["entries"]:
        if e["days_off"]:
            notes.append(f"{e['user']['name']} is out {e['days_off']:g} day{'s' if e['days_off'] != 1 else ''}")
    if unestimated:
        notes.append(f"{unestimated} candidate{'s' if unestimated > 1 else ''} without an estimate")
    blocked = sum(1 for _, i, _ in scored if i.blocked)
    if blocked:
        notes.append(f"{blocked} blocked item{'s' if blocked > 1 else ''} skipped")

    candidates = []
    for s, item, reason in scored:
        d = item_to_dict(item, db)
        d["score"] = s
        d["reason"] = reason
        candidates.append(d)
    return {
        "sprint": cap["sprint"],
        "capacity": cap,
        "candidates": candidates,
        "recommended_ids": recommended,
        "recommended_points": round(total, 1),
        "confidence": confidence,
        "notes": notes,
        "per_person": per_person,
    }


def commit_plan(db: Session, sprint: Sprint, item_ids: list[str], actor: User | None = None) -> Sprint:
    project = sprint.project or db.get(Project, sprint.project_id)
    method = metrics.estimation(project)
    items = [i for i in db.scalars(select(WorkItem).where(WorkItem.id.in_(item_ids))) if i.project_id == project.id]
    try:
        from .items import move_item  # type: ignore
    except ImportError:
        move_item = None
    for item in items:
        if item.sprint_id == sprint.id:
            continue
        moved = False
        if move_item is not None:
            try:
                move_item(db, item, sprint_id=sprint.id, actor=actor)
                moved = True
            except Exception:
                log.debug("services.items.move_item failed; assigning sprint directly", exc_info=True)
                db.rollback()
        if not moved:
            item.sprint_id = sprint.id
            if sprint.state == "active":
                db.add(
                    SprintCommitment(
                        sprint_id=sprint.id, work_item_id=item.id, points=item.points, added_at=utcnow(), added_mid_sprint=True
                    )
                )
    db.flush()
    # planned load per assignee
    by_user: dict[str, list[WorkItem]] = defaultdict(list)
    for item in db.scalars(select(WorkItem).where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False))):
        if item.assignee_id:
            by_user[item.assignee_id].append(item)
    cap = sprint_capacity(db, sprint)
    entries = {e.user_id: e for e in db.scalars(select(CapacityEntry).where(CapacityEntry.sprint_id == sprint.id))}
    for uid, its in by_user.items():
        e = entries.get(uid)
        if e is None:
            user = db.get(User, uid)
            if user is None:
                continue
            e = CapacityEntry(sprint_id=sprint.id, user_id=uid, available_hours=compute_available_hours(user, sprint, project, 0.0))
            db.add(e)
            entries[uid] = e
        e.planned_points = round(sum(float(i.points or 0.0) for i in its), 1)
        e.planned_count = len(its)
    for uid, e in entries.items():
        if uid not in by_user:
            e.planned_points = 0.0
            e.planned_count = 0
    sprint.capacity_points = cap["team_points"]
    sprint.capacity_hours = cap["team_hours"]
    notes = dict(sprint.planning_notes or {})
    notes.update({"method": method, "committed_item_ids": [i.id for i in items], "committed_at": utcnow().isoformat()})
    sprint.planning_notes = notes
    db.commit()
    bus.emit(
        "sprint.updated",
        project_id=sprint.project_id,
        entity_type="sprint",
        entity_id=sprint.id,
        actor_id=actor.id if actor else None,
        data={"plan_committed": len(items)},
    )
    return sprint
