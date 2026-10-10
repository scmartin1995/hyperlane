"""Reports: metrics, burndown/burnup, CFD, cycle time, throughput, Monte Carlo forecast, EVM."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models import Project, Sprint
from ..schemas.common import ProjectOut
from ..services import evm, forecast, metrics
from ..services.auth import DB, CurrentUser

router = APIRouter(tags=["reports"])


def _project(db: Session, pid: str) -> Project:
    project = db.get(Project, pid)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _sprint(db: Session, sid: str) -> Sprint:
    sprint = db.get(Sprint, sid)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    return sprint


# ---- metrics ----


@router.get("/projects/{pid}/metrics/overview")
def metrics_overview(pid: str, db: DB, _: CurrentUser):
    return metrics.overview(db, _project(db, pid))


@router.get("/projects/{pid}/metrics/velocity")
def metrics_velocity(pid: str, db: DB, _: CurrentUser, last: int = Query(8, ge=1, le=50)):
    return metrics.velocity(db, _project(db, pid), last=last)


@router.get("/sprints/{sid}/burndown")
def sprint_burndown(sid: str, db: DB, _: CurrentUser):
    return metrics.burndown(db, _sprint(db, sid))


@router.get("/sprints/{sid}/burnup")
def sprint_burnup(sid: str, db: DB, _: CurrentUser):
    return metrics.burnup(db, _sprint(db, sid))


@router.get("/projects/{pid}/metrics/cfd")
def metrics_cfd(pid: str, db: DB, _: CurrentUser, days: int = Query(60, ge=1, le=365)):
    return metrics.cfd(db, _project(db, pid), days=days)


@router.get("/projects/{pid}/metrics/cycle-time")
def metrics_cycle_time(pid: str, db: DB, _: CurrentUser, days: int = Query(90, ge=1, le=730)):
    return metrics.cycle_time(db, _project(db, pid), days=days)


@router.get("/projects/{pid}/metrics/throughput")
def metrics_throughput(pid: str, db: DB, _: CurrentUser, weeks: int = Query(12, ge=1, le=104)):
    return metrics.throughput(db, _project(db, pid), weeks=weeks)


# ---- forecast ----


@router.get("/projects/{pid}/forecast")
def project_forecast(
    pid: str,
    db: DB,
    _: CurrentUser,
    mode: Literal["how_many", "when"] = "how_many",
    weeks: int | None = Query(None, ge=1, le=104),
    items: int | None = Query(None, ge=1, le=10000),
    sims: int = Query(5000, ge=100, le=50000),
    history_weeks: int = Query(12, ge=1, le=104),
    seed: int | None = None,
):
    return forecast.monte_carlo(
        db, _project(db, pid), mode=mode, weeks=weeks, items=items, sims=sims, history_weeks=history_weeks, seed=seed
    )


# ---- EVM ----


class EvmConfigIn(BaseModel):
    enabled: bool | None = None
    currency: str | None = None
    bac: float | None = None
    cost_per_point: float | None = None
    cost_per_hour: float | None = None
    planned_points: float | None = None
    planned_sprints: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    method: Literal["points", "hours", "count"] | None = None


class SnapshotIn(BaseModel):
    note: str | None = None


@router.get("/projects/{pid}/evm")
def evm_report(pid: str, db: DB, _: CurrentUser):
    return evm.report(db, _project(db, pid))


@router.put("/projects/{pid}/evm/config", response_model=ProjectOut)
def evm_set_config(pid: str, body: EvmConfigIn, db: DB, _: CurrentUser):
    patch: dict[str, Any] = body.model_dump(exclude_unset=True)
    return evm.set_config(db, _project(db, pid), patch)


@router.post("/projects/{pid}/evm/baseline", response_model=ProjectOut)
def evm_lock_baseline(pid: str, db: DB, _: CurrentUser):
    return evm.lock_baseline(db, _project(db, pid))


@router.post("/projects/{pid}/evm/snapshot")
def evm_snapshot(pid: str, db: DB, _: CurrentUser, body: SnapshotIn | None = None):
    snap = evm.snapshot(db, _project(db, pid), note=body.note if body else None)
    return evm.snapshot_to_dict(snap)


@router.get("/projects/{pid}/evm/snapshots")
def evm_snapshots(pid: str, db: DB, _: CurrentUser):
    return [evm.snapshot_to_dict(s) for s in evm.list_snapshots(db, _project(db, pid))]
