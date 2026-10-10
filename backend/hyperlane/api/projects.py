"""Projects, labels, project activity feed, summary."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from ..models import Label, Project
from ..schemas.common import ActivityOut, LabelOut, ProjectOut
from ..schemas.core import LabelIn, LabelPatch, ProjectIn, ProjectPatch
from ..services import projects as svc
from ..services.activity import list_activity
from ..services.auth import DB, CurrentUser, OptionalUser

router = APIRouter(tags=["projects"])


def get_project(db, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _get_label(db, label_id: str) -> Label:
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(404, "Label not found")
    return label


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DB):
    return svc.list_projects(db)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, db: DB, user: OptionalUser):
    """Onboarding: the first project may be created without a session; afterwards a profile is required."""
    if user is None and (db.scalar(select(func.count()).select_from(Project)) or 0) > 0:
        raise HTTPException(401, "Pick a profile first")
    return svc.create_project(db, body.model_dump(exclude_unset=True), user)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def read_project(project_id: str, db: DB):
    return get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectPatch, db: DB, user: CurrentUser):
    return svc.update_project(db, get_project(db, project_id), body.model_dump(exclude_unset=True), user)


@router.delete("/projects/{project_id}", response_model=ProjectOut)
def archive_project(project_id: str, db: DB, user: CurrentUser):
    return svc.archive_project(db, get_project(db, project_id), user)


@router.get("/projects/{project_id}/summary")
def project_summary(project_id: str, db: DB):
    return svc.project_summary(db, get_project(db, project_id))


@router.get("/projects/{project_id}/labels", response_model=list[LabelOut])
def list_labels(project_id: str, db: DB):
    get_project(db, project_id)
    return svc.list_labels(db, project_id)


@router.post("/projects/{project_id}/labels", response_model=LabelOut, status_code=201)
def create_label(project_id: str, body: LabelIn, db: DB, _: CurrentUser):
    return svc.create_label(db, get_project(db, project_id), body.name, body.color)


@router.patch("/labels/{label_id}", response_model=LabelOut)
def update_label(label_id: str, body: LabelPatch, db: DB, _: CurrentUser):
    return svc.update_label(db, _get_label(db, label_id), body.model_dump(exclude_unset=True))


@router.delete("/labels/{label_id}")
def delete_label(label_id: str, db: DB, _: CurrentUser):
    svc.delete_label(db, _get_label(db, label_id))
    return {"ok": True}


@router.get("/projects/{project_id}/activity", response_model=list[ActivityOut])
def project_activity(
    project_id: str, db: DB, limit: int = 50, entity_type: str | None = None, entity_id: str | None = None
):
    get_project(db, project_id)
    return list_activity(db, project_id=project_id, entity_type=entity_type, entity_id=entity_id, limit=min(limit, 500))
