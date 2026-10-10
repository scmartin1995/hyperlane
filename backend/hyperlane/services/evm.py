"""AgileEVM: earned value on top of points / hours / counts.

Formulas (all money in the project's currency, BAC from `project.evm`):
  PV = BAC x planned-progress fraction
       - sprints:      closed sprints / planned_sprints              (when planned_sprints > 0 and sprints exist)
       - working days: elapsed working days / total working days    (start_date..end_date, clamped 0..1)
  EV = BAC x completed / planned_points  (planned_points = baseline, or current scope when not locked;
       "points" sums story points, "hours" sums estimate_hours, "count" counts items)
  AC = sum over items of: actual_cost if set, else actual_hours x cost_per_hour, else (done items only)
       points x cost_per_point
  SV = EV - PV, CV = EV - AC, SPI = EV / PV, CPI = EV / AC, EAC = BAC / CPI, ETC = EAC - AC,
  VAC = BAC - EAC, TCPI = (BAC - EV) / (BAC - AC)
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope, utcnow
from ..models import EvmSnapshot, Project, Sprint, WorkItem
from . import metrics
from .events import bus
from .scheduler import register_job
from .templates import default_evm

log = logging.getLogger(__name__)

MAX_SERIES_DAYS = 730


def config(project: Project) -> dict[str, Any]:
    return {**default_evm(), **(project.evm or {})}


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _working_days(project: Project) -> set[int]:
    wd = (project.settings or {}).get("working_days") or [0, 1, 2, 3, 4]
    return {int(x) for x in wd}


def _count_working_days(start: date, end: date, working: set[int]) -> int:
    if end < start:
        return 0
    n = 0
    d = start
    while d <= end:
        if d.weekday() in working:
            n += 1
        d += timedelta(days=1)
    return n


def _value(item: WorkItem, method: str) -> float:
    if method == "count":
        return 1.0
    if method == "hours":
        return float(item.estimate_hours or 0.0)
    return float(item.points or 0.0)


def _item_cost(item: WorkItem, cfg: dict[str, Any], done: bool) -> float:
    if item.actual_cost is not None:
        return float(item.actual_cost)
    if item.actual_hours and cfg.get("cost_per_hour"):
        return float(item.actual_hours) * float(cfg["cost_per_hour"])
    if done and cfg.get("cost_per_point"):
        return float(item.points or 0.0) * float(cfg["cost_per_point"])
    return 0.0


def _safe_div(a: float, b: float, default: float = 1.0) -> float:
    return a / b if b else default


class _Plan:
    """Planned-progress fraction as a function of date."""

    def __init__(self, db: Session, project: Project, cfg: dict[str, Any]):
        self.start = _parse_date(cfg.get("start_date"))
        self.end = _parse_date(cfg.get("end_date"))
        self.working = _working_days(project)
        self.planned_sprints = int(cfg.get("planned_sprints") or 0)
        sprints = list(db.scalars(select(Sprint).where(Sprint.project_id == project.id)))
        self.closed_on: list[date] = sorted(
            (s.closed_at.date() if s.closed_at else s.end_date) for s in sprints if s.state == "closed"
        )
        self.has_sprints = bool(sprints)
        if self.start is None and sprints:
            self.start = min(s.start_date for s in sprints)
        if self.planned_sprints > 0 and self.has_sprints:
            self.method = "sprints"
        elif self.start and self.end and self.end >= self.start:
            self.method = "working_days"
        else:
            self.method = "none"
        self.total_working = _count_working_days(self.start, self.end, self.working) if self.method == "working_days" else 0

    def fraction(self, d: date) -> float:
        if self.method == "sprints":
            closed = sum(1 for c in self.closed_on if c <= d)
            return max(0.0, min(1.0, closed / self.planned_sprints))
        if self.method == "working_days":
            if d < self.start:
                return 0.0
            if d >= self.end:
                return 1.0
            if self.total_working == 0:
                return 1.0
            return max(0.0, min(1.0, _count_working_days(self.start, d, self.working) / self.total_working))
        return 0.0

    def describe(self) -> str:
        if self.method == "sprints":
            return f"Planned value counts closed sprints against {self.planned_sprints} planned."
        if self.method == "working_days":
            return f"Planned value follows working days between {self.start.isoformat()} and {self.end.isoformat()}."
        return "Planned value needs start/end dates or a planned sprint count."


def _core(bac: float, pv: float, ev: float, ac: float) -> dict[str, float]:
    spi = _safe_div(ev, pv, 1.0)
    cpi = _safe_div(ev, ac, 1.0)
    eac = bac / cpi if cpi > 0 else bac
    etc = eac - ac
    vac = bac - eac
    remaining_budget = bac - ac
    tcpi = (bac - ev) / remaining_budget if remaining_budget > 0 else 0.0
    return {
        "sv": round(ev - pv, 2),
        "cv": round(ev - ac, 2),
        "spi": round(spi, 3),
        "cpi": round(cpi, 3),
        "eac": round(eac, 2),
        "etc": round(etc, 2),
        "vac": round(vac, 2),
        "tcpi": round(tcpi, 3),
        "pct_complete": round(_safe_div(ev, bac, 0.0) * 100, 1),
        "pct_planned": round(_safe_div(pv, bac, 0.0) * 100, 1),
        "pct_spent": round(_safe_div(ac, bac, 0.0) * 100, 1),
    }


def _status(enabled: bool, bac: float, spi: float, cpi: float) -> str:
    if not enabled or bac <= 0:
        return "not_configured"
    if spi >= 0.95 and cpi >= 0.95:
        return "on_track"
    if spi >= 0.85 and cpi >= 0.85:
        return "at_risk"
    return "off_track"


def _compute(db: Session, project: Project) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = config(project)
    tdy = metrics.today()
    bac = float(cfg.get("bac") or 0.0)
    method = cfg.get("method") or "points"
    currency = cfg.get("currency") or "USD"
    done_keys = metrics.done_statuses(project)
    items = list(db.scalars(select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.is_archived.is_(False))))
    scope = sum(_value(i, method) for i in items)
    planned_points = float(cfg.get("planned_points") or 0.0) or scope
    done_items = [i for i in items if i.status in done_keys]
    completed = sum(_value(i, method) for i in done_items)
    plan = _Plan(db, project, cfg)

    pv = bac * plan.fraction(tdy)
    ev = bac * _safe_div(completed, planned_points, 0.0)
    ac = sum(_item_cost(i, cfg, i.status in done_keys) for i in items)
    core = _core(bac, pv, ev, ac)
    status = _status(bool(cfg.get("enabled")), bac, core["spi"], core["cpi"])

    forecast_end: str | None = None
    if plan.end and core["spi"] > 0 and bac > 0:
        remaining = (plan.end - tdy).days
        if remaining <= 0 and plan.start:
            total = max(1, (plan.end - plan.start).days)
            remaining = total * (1 - _safe_div(ev, bac, 0.0))
        forecast_end = (tdy + timedelta(days=math.ceil(remaining / core["spi"]))).isoformat()

    # ---- series ----
    series: list[dict[str, Any]] = []
    start = plan.start or (min((i.created_at.date() for i in items), default=tdy))
    if (tdy - start).days > MAX_SERIES_DAYS:
        start = tdy - timedelta(days=MAX_SERIES_DAYS)
    snaps = {
        s.as_of: s
        for s in db.scalars(select(EvmSnapshot).where(EvmSnapshot.project_id == project.id, EvmSnapshot.as_of <= tdy))
    }
    done_sorted = sorted((i for i in done_items if i.completed_at), key=lambda i: i.completed_at)
    d = start
    idx = 0
    ev_cum = 0.0
    ac_cum = 0.0
    while d <= tdy:
        while idx < len(done_sorted) and done_sorted[idx].completed_at.date() <= d:
            it = done_sorted[idx]
            ev_cum += _value(it, method)
            ac_cum += _item_cost(it, cfg, True)
            idx += 1
        snap = snaps.get(d)
        if snap is not None:
            point = {"date": d.isoformat(), "pv": round(snap.pv, 2), "ev": round(snap.ev, 2), "ac": round(snap.ac, 2), "sprint_id": snap.sprint_id}
        elif d == tdy:
            point = {"date": d.isoformat(), "pv": round(pv, 2), "ev": round(ev, 2), "ac": round(ac, 2), "sprint_id": None}
        else:
            point = {
                "date": d.isoformat(),
                "pv": round(bac * plan.fraction(d), 2),
                "ev": round(bac * _safe_div(ev_cum, planned_points, 0.0), 2),
                "ac": round(ac_cum, 2),
                "sprint_id": None,
            }
        series.append(point)
        d += timedelta(days=1)

    # ---- narrative ----
    if status == "not_configured":
        narrative = "Earned value is not configured yet: enable it and set a budget at completion (BAC) to start tracking. " + plan.describe()
    else:
        ahead = "ahead of" if core["spi"] >= 1 else "behind"
        over = "under" if core["vac"] >= 0 else "over"
        parts = [
            f"{core['pct_complete']:.0f}% of the value is earned against {core['pct_planned']:.0f}% planned, so the work is {ahead} schedule (SPI {core['spi']:.2f}).",
            f"{core['pct_spent']:.0f}% of the {currency} {bac:,.0f} budget is spent (CPI {core['cpi']:.2f}); at this rate the project lands at {currency} {core['eac']:,.0f}, {over} budget by {currency} {abs(core['vac']):,.0f}"
            + (f", finishing around {forecast_end}." if forecast_end else "."),
            plan.describe(),
        ]
        narrative = " ".join(parts)

    report = {
        "config": cfg,
        "as_of": tdy.isoformat(),
        "bac": round(bac, 2),
        "pv": round(pv, 2),
        "ev": round(ev, 2),
        "ac": round(ac, 2),
        **core,
        "forecast_end_date": forecast_end,
        "series": series,
        "status": status,
        "narrative": narrative,
    }
    extras = {"planned_points": planned_points, "completed_points": completed, "total_points": scope}
    return report, extras


def report(db: Session, project: Project) -> dict[str, Any]:
    return _compute(db, project)[0]


# ---------------------------------------------------------------------------
# configuration / baseline / snapshots
# ---------------------------------------------------------------------------

_CONFIG_KEYS = set(default_evm().keys())


def set_config(db: Session, project: Project, patch: dict[str, Any]) -> Project:
    cfg = config(project)
    for k, v in patch.items():
        if k not in _CONFIG_KEYS:
            continue
        if k in ("start_date", "end_date"):
            v = _parse_date(v).isoformat() if _parse_date(v) else None
        elif k == "method":
            if v not in ("points", "hours", "count"):
                raise ValueError("method must be points, hours or count")
        elif k in ("bac", "cost_per_point", "cost_per_hour", "planned_points"):
            v = float(v or 0.0)
        elif k == "planned_sprints":
            v = int(v or 0)
        cfg[k] = v
    project.evm = cfg
    db.commit()
    bus.emit("project.updated", project_id=project.id, entity_type="project", entity_id=project.id, data={"evm": True})
    return project


def lock_baseline(db: Session, project: Project) -> Project:
    cfg = config(project)
    method = cfg.get("method") or "points"
    items = list(db.scalars(select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.is_archived.is_(False))))
    cfg["planned_points"] = round(sum(_value(i, method) for i in items), 2)
    sprints = list(db.scalars(select(Sprint).where(Sprint.project_id == project.id).order_by(Sprint.number)))
    length = int((project.settings or {}).get("sprint_length_days") or 14)
    start = _parse_date(cfg.get("start_date")) or (sprints[0].start_date if sprints else metrics.today())
    end = _parse_date(cfg.get("end_date")) or _parse_date((project.settings or {}).get("target_end_date"))
    planned_sprints = int(cfg.get("planned_sprints") or 0)
    if planned_sprints <= 0:
        if end:
            planned_sprints = max(1, math.ceil(((end - start).days + 1) / length))
        else:
            planned_sprints = len(sprints)
    if end is None and planned_sprints > 0:
        end = start + timedelta(days=planned_sprints * length - 1)
    cfg["planned_sprints"] = planned_sprints
    cfg["start_date"] = start.isoformat()
    cfg["end_date"] = end.isoformat() if end else None
    cfg["baseline_locked_at"] = utcnow().isoformat()
    project.evm = cfg
    db.commit()
    bus.emit("project.updated", project_id=project.id, entity_type="project", entity_id=project.id, data={"evm": True, "baseline": True})
    return project


def snapshot(db: Session, project: Project, note: str | None = None) -> EvmSnapshot:
    rep, extras = _compute(db, project)
    tdy = metrics.today()
    snap = db.scalar(select(EvmSnapshot).where(EvmSnapshot.project_id == project.id, EvmSnapshot.as_of == tdy))
    if snap is None:
        snap = EvmSnapshot(project_id=project.id, as_of=tdy)
        db.add(snap)
    active = db.scalar(select(Sprint).where(Sprint.project_id == project.id, Sprint.state == "active"))
    snap.sprint_id = active.id if active else None
    snap.bac = rep["bac"]
    snap.pv = rep["pv"]
    snap.ev = rep["ev"]
    snap.ac = rep["ac"]
    snap.planned_points = round(extras["planned_points"], 2)
    snap.completed_points = round(extras["completed_points"], 2)
    snap.total_points = round(extras["total_points"], 2)
    snap.metrics = {
        k: rep[k]
        for k in ("sv", "cv", "spi", "cpi", "eac", "etc", "vac", "tcpi", "pct_complete", "pct_planned", "pct_spent", "status")
    }
    if note is not None:
        snap.note = note
    db.commit()
    bus.emit("evm.snapshot", project_id=project.id, entity_type="evm_snapshot", entity_id=snap.id, data={"as_of": tdy.isoformat()})
    return snap


def list_snapshots(db: Session, project: Project) -> list[EvmSnapshot]:
    return list(db.scalars(select(EvmSnapshot).where(EvmSnapshot.project_id == project.id).order_by(EvmSnapshot.as_of)))


def daily_snapshots() -> None:
    """Scheduler job: snapshot every active project that has EVM enabled."""
    with session_scope() as db:
        for project in db.scalars(select(Project).where(Project.status == "active")):
            if not config(project).get("enabled"):
                continue
            try:
                snapshot(db, project, note="daily")
            except Exception:  # pragma: no cover
                log.exception("EVM snapshot failed for project %s", project.id)


register_job(daily_snapshots, trigger="cron", hour=23, minute=55, id="evm-daily", replace_existing=True)


def snapshot_to_dict(snap: EvmSnapshot) -> dict[str, Any]:
    return {
        "id": snap.id,
        "project_id": snap.project_id,
        "as_of": snap.as_of.isoformat(),
        "sprint_id": snap.sprint_id,
        "bac": snap.bac,
        "pv": snap.pv,
        "ev": snap.ev,
        "ac": snap.ac,
        "planned_points": snap.planned_points,
        "completed_points": snap.completed_points,
        "total_points": snap.total_points,
        "metrics": snap.metrics or {},
        "note": snap.note,
        "created_at": snap.created_at.isoformat() if isinstance(snap.created_at, datetime) else None,
    }
