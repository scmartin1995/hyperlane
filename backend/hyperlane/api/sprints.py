"""Sprints: plan, start, close (with carry-over)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import Sprint
from ..schemas.common import SprintOut, WorkItemOut
from ..schemas.core import SprintCloseIn, SprintIn
from ..services import sprints as svc
from ..services.auth import DB, CurrentUser
from ..services.items import serialize_items
from .projects import get_project

router = APIRouter(tags=["sprints"])


def get_sprint(db, sprint_id: str) -> Sprint:
    sprint = db.get(Sprint, sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    return sprint


@router.get("/projects/{project_id}/sprints", response_model=list[SprintOut])
def list_sprints(project_id: str, db: DB, state: str | None = None):
    get_project(db, project_id)
    return svc.list_sprints(db, project_id, state=state)


@router.post("/projects/{project_id}/sprints", response_model=SprintOut, status_code=201)
def create_sprint(project_id: str, body: SprintIn, db: DB, user: CurrentUser):
    return svc.create_sprint(db, get_project(db, project_id), body.model_dump(exclude_unset=True), user)


@router.get("/sprints/{sprint_id}", response_model=SprintOut)
def read_sprint(sprint_id: str, db: DB):
    return get_sprint(db, sprint_id)


@router.patch("/sprints/{sprint_id}", response_model=SprintOut)
def update_sprint(sprint_id: str, body: SprintIn, db: DB, user: CurrentUser):
    return svc.update_sprint(db, get_sprint(db, sprint_id), body.model_dump(exclude_unset=True), user)


@router.delete("/sprints/{sprint_id}")
def delete_sprint(sprint_id: str, db: DB, user: CurrentUser):
    svc.delete_sprint(db, get_sprint(db, sprint_id), user)
    return {"ok": True}


@router.get("/sprints/{sprint_id}/items", response_model=list[WorkItemOut])
def sprint_items(sprint_id: str, db: DB):
    return serialize_items(svc.sprint_items(db, get_sprint(db, sprint_id)), db)


@router.post("/sprints/{sprint_id}/start", response_model=SprintOut)
def start_sprint(sprint_id: str, db: DB, user: CurrentUser):
    return svc.start_sprint(db, get_sprint(db, sprint_id), user)


@router.post("/sprints/{sprint_id}/close")
def close_sprint(sprint_id: str, body: SprintCloseIn, db: DB, user: CurrentUser):
    return svc.close_sprint(db, get_sprint(db, sprint_id), body.carry_over, user)
