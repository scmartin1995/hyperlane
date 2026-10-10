"""Excel / CSV import into a project's backlog."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..agent import _compat as c
from ..agent import importer
from ..models import Project
from ..schemas.common import ImportPreviewOut
from ..services.auth import DB, CurrentUser

router = APIRouter(tags=["imports"])

MAX_UPLOAD = 25 * 1024 * 1024


class CommitIn(BaseModel):
    file_token: str
    sheet: str | None = None
    mapping: dict[str, str | None]
    create_missing_users: bool = False


def _project(db, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/projects/{project_id}/import/excel/preview", response_model=ImportPreviewOut)
async def preview(
    project_id: str,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    sheet: Annotated[str | None, Form()] = None,
):
    project = _project(db, project_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is too large (25 MB max)")
    try:
        return await importer.preview(project, data, file.filename or "upload.xlsx", sheet)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read the file: {exc}") from exc


@router.post("/projects/{project_id}/import/excel/commit")
def commit(project_id: str, body: CommitIn, db: DB, user: CurrentUser):
    project = _project(db, project_id)
    result = importer.commit(db, project, body.file_token, body.sheet, body.mapping, body.create_missing_users, user)
    db.commit()
    created = result["created"]
    for it in created:
        db.refresh(it)
    return {
        "created": [c.item_out(db, it) for it in created],
        "skipped": result["skipped"],
        "warnings": result["warnings"],
    }
