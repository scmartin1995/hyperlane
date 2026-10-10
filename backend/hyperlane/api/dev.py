"""Demo data for the welcome flow ("Load demo league")."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.core import SeedIn
from ..services.auth import DB
from ..services.seed import seed

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/seed")
def run_seed(db: DB, body: SeedIn | None = None):
    return seed((body or SeedIn()).project_name, db=db)
