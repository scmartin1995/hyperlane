"""Global search (command palette)."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.common import WorkItemOut
from ..services import items as svc
from ..services.auth import DB

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[WorkItemOut])
def search(db: DB, q: str = "", limit: int = 20):
    return svc.serialize_items(svc.search_items(db, q, limit=min(max(limit, 1), 100)), db)
