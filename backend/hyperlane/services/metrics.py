"""Agile metrics: velocity, burndown/burnup, cumulative flow, cycle time, throughput, health.

Everything here is read-only and reconstructs history from `StatusTransition`, `completed_at`
and `SprintCommitment` rows. Values are expressed in the project's estimation unit
(`settings.estimation`: points | hours | throughput, where throughput means item count).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Project, Sprint, SprintCommitment, StatusTransition, WorkItem
from ..schemas.common import SprintOut

# ---------------------------------------------------------------------------
# shared helpers (also used by forecast / evm / capacity / retro)
# ---------------------------------------------------------------------------


def today() -> date:
    return utcnow().date()


def estimation(project: Project) -> str:
    mode = (project.settings or {}).get("estimation", "points")
    return mode if mode in ("points", "hours", "throughput") else "points"


def categories(project: Project) -> dict[str, str]:
    """status key -> category (todo | in_progress | done)."""
    return {s["key"]: s.get("category", "todo") for s in (project.workflow or [])}


def done_statuses(project: Project) -> set[str]:
    return {k for k, c in categories(project).items() if c == "done"}


def item_value(item: WorkItem, mode: str) -> float:
    """Size of an item in the project's estimation unit."""
    if mode == "throughput":
        return 1.0
    if mode == "hours":
        return float(item.estimate_hours or 0.0)
    return float(item.points or 0.0)


def is_done(item: WorkItem, project: Project) -> bool:
    return item.status in done_statuses(project)


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in 0..100). 0 for an empty list."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return float(xs[lo] + (xs[hi] - xs[lo]) * frac)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _days(delta: timedelta) -> float:
    return round(delta.total_seconds() / 86400.0, 2)


def _project_items(db: Session, project: Project, *, include_archived: bool = False) -> list[WorkItem]:
    q = select(WorkItem).where(WorkItem.project_id == project.id)
    if not include_archived:
        q = q.where(WorkItem.is_archived.is_(False))
    return list(db.scalars(q))


def _transitions_by_item(db: Session, project: Project) -> dict[str, list[StatusTransition]]:
    out: dict[str, list[StatusTransition]] = defaultdict(list)
    for t in db.scalars(
        select(StatusTransition)
        .where(StatusTransition.project_id == project.id)
        .order_by(StatusTransition.at, StatusTransition.id)
    ):
        out[t.work_item_id].append(t)
    return out


# ---------------------------------------------------------------------------
# velocity
# ---------------------------------------------------------------------------


def _sprint_velocity(db: Session, project: Project, sprint: Sprint, mode: str) -> tuple[float, float]:
    """(committed, completed) for a sprint in the estimation unit."""
    if mode == "points" and (sprint.committed_points or sprint.completed_points):
        return float(sprint.committed_points or 0), float(sprint.completed_points or 0)
    if mode == "throughput" and (sprint.committed_count or sprint.completed_count):
        return float(sprint.committed_count or 0), float(sprint.completed_count or 0)
    # fall back to the items that are (still) in the sprint
    items = list(db.scalars(select(WorkItem).where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False))))
    committed = sum(item_value(i, mode) for i in items)
    completed = sum(item_value(i, mode) for i in items if is_done(i, project))
    return committed, completed


def velocity(db: Session, project: Project, last: int = 8) -> list[dict[str, Any]]:
    mode = estimation(project)
    sprints = list(
        db.scalars(
            select(Sprint)
            .where(Sprint.project_id == project.id, Sprint.state == "closed")
            .order_by(Sprint.number.desc())
            .limit(last)
        )
    )
    sprints.reverse()
    out = []
    for s in sprints:
        committed, completed = _sprint_velocity(db, project, s, mode)
        out.append({"sprint": s.name, "sprint_id": s.id, "committed": round(committed, 2), "completed": round(completed, 2)})
    return out


def _trend_percent(values: list[float]) -> float:
    """Least-squares slope over the window, as a percent of the mean per sprint."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = _mean(values)
    if mean == 0:
        return 0.0
    xs = list(range(n))
    xm = _mean([float(x) for x in xs])
    num = sum((x - xm) * (y - mean) for x, y in zip(xs, values, strict=True))
    den = sum((x - xm) ** 2 for x in xs)
    slope = num / den if den else 0.0
    return round(slope / mean * 100.0, 1)


# ---------------------------------------------------------------------------
# cycle time / throughput / flow
# ---------------------------------------------------------------------------


def _first_in_progress(trs: list[StatusTransition]) -> datetime | None:
    for t in trs:
        if t.to_category == "in_progress":
            return t.at
    return None


def cycle_time(db: Session, project: Project, days: int = 90) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    done = done_statuses(project)
    trs = _transitions_by_item(db, project)
    points: list[dict[str, Any]] = []
    for item in _project_items(db, project):
        if item.status not in done or item.completed_at is None or item.completed_at < since:
            continue
        start = _first_in_progress(trs.get(item.id, [])) or item.started_at or item.created_at
        cycle = max(0.0, _days(item.completed_at - start))
        lead = max(0.0, _days(item.completed_at - item.created_at))
        points.append(
            {
                "item_id": item.id,
                "key": f"{project.key}-{item.number}",
                "title": item.title,
                "type": item.type,
                "completed_at": item.completed_at.isoformat(),
                "cycle_days": cycle,
                "lead_days": lead,
            }
        )
    points.sort(key=lambda p: p["completed_at"])
    cycles = [p["cycle_days"] for p in points]
    by_type: dict[str, list[float]] = defaultdict(list)
    for p in points:
        by_type[p["type"]].append(p["cycle_days"])
    return {
        "points": points,
        "p50": round(percentile(cycles, 50), 2),
        "p85": round(percentile(cycles, 85), 2),
        "p95": round(percentile(cycles, 95), 2),
        "avg": round(_mean(cycles), 2),
        "by_type": {k: round(_mean(v), 2) for k, v in sorted(by_type.items())},
    }


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def throughput(db: Session, project: Project, weeks: int = 12) -> dict[str, Any]:
    """Weekly (Monday-start) buckets of done items; the last bucket is the current, partial week."""
    weeks = max(1, weeks)
    first = week_start(today()) - timedelta(weeks=weeks - 1)
    buckets: dict[date, dict[str, float]] = {
        first + timedelta(weeks=i): {"count": 0, "points": 0.0} for i in range(weeks)
    }
    done = done_statuses(project)
    for item in _project_items(db, project):
        if item.status not in done or item.completed_at is None:
            continue
        ws = week_start(item.completed_at.date())
        if ws in buckets:
            buckets[ws]["count"] += 1
            buckets[ws]["points"] += float(item.points or 0.0)
    rows = [
        {"week_start": ws.isoformat(), "count": int(v["count"]), "points": round(v["points"], 2)}
        for ws, v in sorted(buckets.items())
    ]
    return {
        "weeks": rows,
        "avg_count": round(_mean([float(r["count"]) for r in rows]), 2),
        "avg_points": round(_mean([float(r["points"]) for r in rows]), 2),
    }


def flow_efficiency(db: Session, project: Project, days: int = 90) -> float | None:
    """Active time (in an in_progress state) / lead time (created -> done), over recent done items.

    Returns None when no done item has transition history to compute it from.
    """
    since = utcnow() - timedelta(days=days)
    done = done_statuses(project)
    trs = _transitions_by_item(db, project)
    active_total = 0.0
    lead_total = 0.0
    for item in _project_items(db, project):
        if item.status not in done or item.completed_at is None or item.completed_at < since:
            continue
        history = trs.get(item.id)
        if not history:
            continue
        active = 0.0
        current_cat = history[0].from_category or "todo"
        cursor = item.created_at
        for t in history:
            if current_cat == "in_progress":
                active += (t.at - cursor).total_seconds()
            cursor = t.at
            current_cat = t.to_category
        lead = (item.completed_at - item.created_at).total_seconds()
        if lead <= 0:
            continue
        active_total += active
        lead_total += lead
    if lead_total <= 0:
        return None
    return round(min(1.0, active_total / lead_total), 3)


# ---------------------------------------------------------------------------
# overview + health
# ---------------------------------------------------------------------------


def _signal(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def overview(db: Session, project: Project) -> dict[str, Any]:
    mode = estimation(project)
    cats = categories(project)
    done = {k for k, c in cats.items() if c == "done"}
    unit = "items" if mode == "throughput" else ("h" if mode == "hours" else "pts")
    now = utcnow()
    tdy = now.date()

    vel = velocity(db, project, last=8)
    completed = [v["completed"] for v in vel]
    avg_velocity = round(_mean(completed[-5:]), 2)
    velocity_trend = _trend_percent(completed[-6:])

    items = _project_items(db, project)
    four_weeks_ago = now - timedelta(days=28)
    done_recent = [i for i in items if i.status in done and i.completed_at and i.completed_at >= four_weeks_ago]
    throughput_per_week = round(len(done_recent) / 4.0, 2)

    ct = cycle_time(db, project, days=90)

    open_items = [i for i in items if i.status not in done]
    wip_items = [i for i in open_items if cats.get(i.status) == "in_progress"]
    by_status: dict[str, int] = defaultdict(int)
    for i in items:
        by_status[i.status] += 1
    breaches = []
    for state in project.workflow or []:
        limit = state.get("wip_limit")
        if limit and by_status.get(state["key"], 0) > limit:
            breaches.append({"status": state["key"], "count": by_status[state["key"]], "limit": int(limit)})

    blocked = sum(1 for i in open_items if i.blocked)
    overdue = sum(1 for i in open_items if i.due_date and i.due_date < tdy)
    fe = flow_efficiency(db, project)

    active = db.scalars(
        select(Sprint).where(Sprint.project_id == project.id, Sprint.state == "active").order_by(Sprint.number.desc())
    ).first()
    active_out = None
    if active is not None:
        total_days = max(1, (active.end_date - active.start_date).days + 1)
        elapsed = min(total_days, max(0, (tdy - active.start_date).days + (1 if tdy >= active.start_date else 0)))
        pct_time = round(100.0 * elapsed / total_days, 1)
        sprint_items = [i for i in items if i.sprint_id == active.id]
        scope = sum(item_value(i, mode) for i in sprint_items)
        done_val = sum(item_value(i, mode) for i in sprint_items if i.status in done)
        pct_scope = round(100.0 * done_val / scope, 1) if scope > 0 else 0.0
        days_left = max(0, (active.end_date - tdy).days)
        on_track = pct_scope >= 100.0 or pct_scope >= pct_time - 15.0
        active_out = {
            "sprint": SprintOut.model_validate(active).model_dump(mode="json"),
            "pct_time": pct_time,
            "pct_scope_done": pct_scope,
            "on_track": on_track,
            "days_left": days_left,
        }

    # ---- health score ----
    score = 100.0
    signals: list[dict[str, str]] = []
    names = {s["key"]: s["name"] for s in project.workflow or []}
    if breaches:
        for b in breaches:
            signals.append(_signal("wip", "bad", f"WIP {b['count']} over limit {b['limit']} in {names.get(b['status'], b['status'])}"))
        score -= min(30, 15 * len(breaches))
    else:
        signals.append(_signal("wip", "good", f"{len(wip_items)} in progress" + (", within limits" if any(s.get("wip_limit") for s in project.workflow or []) else "")))

    if len(completed) >= 2:
        if velocity_trend <= -15:
            signals.append(_signal("velocity", "bad", f"Velocity trending down {abs(velocity_trend):.0f}%"))
            score -= 15
        elif velocity_trend < -5:
            signals.append(_signal("velocity", "warn", f"Velocity trending down {abs(velocity_trend):.0f}%"))
            score -= 8
        elif velocity_trend > 5:
            signals.append(_signal("velocity", "good", f"Velocity trending up {velocity_trend:.0f}%"))
        else:
            signals.append(_signal("velocity", "good", f"Velocity steady at ~{avg_velocity:g} {unit}"))
    else:
        signals.append(_signal("velocity", "warn", "Not enough closed sprints to judge velocity"))
        score -= 3

    if blocked >= 3:
        signals.append(_signal("blocked", "bad", f"{blocked} blocked items"))
        score -= 15
    elif blocked:
        signals.append(_signal("blocked", "warn", f"{blocked} blocked item{'s' if blocked > 1 else ''}"))
        score -= 5 * blocked
    else:
        signals.append(_signal("blocked", "good", "Nothing blocked"))

    if overdue >= 3:
        signals.append(_signal("overdue", "bad", f"{overdue} overdue items"))
        score -= 15
    elif overdue:
        signals.append(_signal("overdue", "warn", f"{overdue} overdue item{'s' if overdue > 1 else ''}"))
        score -= 5 * overdue
    else:
        signals.append(_signal("overdue", "good", "Nothing overdue"))

    if active_out is not None:
        if active_out["on_track"]:
            signals.append(_signal("sprint", "good", f"Sprint {active_out['pct_scope_done']:.0f}% done with {active_out['pct_time']:.0f}% of time used"))
        else:
            gap = active_out["pct_time"] - active_out["pct_scope_done"]
            status = "bad" if gap > 30 else "warn"
            signals.append(_signal("sprint", status, f"Sprint {active_out['pct_scope_done']:.0f}% done but {active_out['pct_time']:.0f}% of time used"))
            score -= 15 if status == "bad" else 8

    if fe is not None:
        if fe < 0.25:
            signals.append(_signal("flow", "warn", f"Flow efficiency {fe * 100:.0f}% (lots of waiting)"))
            score -= 5
        else:
            signals.append(_signal("flow", "good", f"Flow efficiency {fe * 100:.0f}%"))

    score = max(0.0, min(100.0, score))
    label = "Healthy" if score >= 80 else ("Watch" if score >= 60 else "At risk")

    return {
        "project_id": project.id,
        "as_of": tdy.isoformat(),
        "velocity": vel,
        "avg_velocity": avg_velocity,
        "velocity_trend": velocity_trend,
        "throughput_per_week": throughput_per_week,
        "avg_cycle_time_days": ct["avg"],
        "p85_cycle_time_days": ct["p85"],
        "wip": len(wip_items),
        "wip_limit_breaches": breaches,
        "flow_efficiency": fe,
        "blocked": blocked,
        "overdue": overdue,
        "active_sprint": active_out,
        "health": {"score": round(score), "label": label, "signals": signals},
    }


# ---------------------------------------------------------------------------
# burndown / burnup
# ---------------------------------------------------------------------------


def _sprint_scope_rows(db: Session, sprint: Sprint, project: Project, mode: str) -> list[tuple[WorkItem, float, date, date | None]]:
    """(item, value, added_on, removed_on) for everything that was ever in the sprint."""
    commits = list(db.scalars(select(SprintCommitment).where(SprintCommitment.sprint_id == sprint.id)))
    rows: list[tuple[WorkItem, float, date, date | None]] = []
    if commits:
        ids = {c.work_item_id for c in commits}
        items = {i.id: i for i in db.scalars(select(WorkItem).where(WorkItem.id.in_(ids)))}
        for c in commits:
            item = items.get(c.work_item_id)
            if item is None:
                continue
            value = float(c.points) if (mode == "points" and c.points is not None) else item_value(item, mode)
            rows.append((item, value, c.added_at.date(), c.removed_at.date() if c.removed_at else None))
    else:
        items = list(db.scalars(select(WorkItem).where(WorkItem.sprint_id == sprint.id, WorkItem.is_archived.is_(False))))
        rows = [(i, item_value(i, mode), sprint.start_date, None) for i in items]
    return rows


def _sprint_series(db: Session, sprint: Sprint) -> list[dict[str, Any]]:
    project = sprint.project or db.get(Project, sprint.project_id)
    mode = estimation(project)
    rows = _sprint_scope_rows(db, sprint, project, mode)
    tdy = today()
    n_days = max(1, (sprint.end_date - sprint.start_date).days + 1)
    scope0 = sum(v for _, v, added, _r in rows if added <= sprint.start_date)
    out = []
    for i in range(n_days):
        d = sprint.start_date + timedelta(days=i)
        future = d > tdy
        eff = min(d, tdy) if future else d
        scope = sum(v for _, v, added, removed in rows if added <= eff and (removed is None or removed > eff))
        done_val = sum(
            v
            for item, v, added, removed in rows
            if added <= eff and (removed is None or removed > eff) and item.completed_at and item.completed_at.date() <= eff
        )
        ideal = scope0 * (1 - i / (n_days - 1)) if n_days > 1 else 0.0
        out.append(
            {
                "date": d.isoformat(),
                "ideal": round(ideal, 2),
                "remaining": None if future else round(scope - done_val, 2),
                "scope": round(scope, 2),
                "done": None if future else round(done_val, 2),
            }
        )
    return out


def burndown(db: Session, sprint: Sprint) -> list[dict[str, Any]]:
    return _sprint_series(db, sprint)


def burnup(db: Session, sprint: Sprint) -> list[dict[str, Any]]:
    return _sprint_series(db, sprint)


# ---------------------------------------------------------------------------
# cumulative flow
# ---------------------------------------------------------------------------


def cfd(db: Session, project: Project, days: int = 60) -> list[dict[str, Any]]:
    days = max(1, days)
    states = [s["key"] for s in project.workflow or []]
    trs = _transitions_by_item(db, project)
    tdy = today()
    first_day = tdy - timedelta(days=days - 1)
    items = _project_items(db, project)

    # per item: sorted list of (effective_date, status) change points, starting at creation
    timelines: list[tuple[date, list[tuple[date, str]]]] = []
    for item in items:
        history = trs.get(item.id, [])
        initial = history[0].from_status if history and history[0].from_status else (item.status if not history else history[0].to_status)
        points = [(item.created_at.date(), initial)]
        points.extend((t.at.date(), t.to_status) for t in history)
        timelines.append((item.created_at.date(), points))

    out = []
    for i in range(days):
        d = first_day + timedelta(days=i)
        counts = dict.fromkeys(states, 0)
        for created, points in timelines:
            if created > d:
                continue
            status = points[0][1]
            for when, st in points:
                if when <= d:
                    status = st
                else:
                    break
            counts[status] = counts.get(status, 0) + 1
        row: dict[str, Any] = {"date": d.isoformat()}
        row.update(counts)
        out.append(row)
    return out
