"""First-run setup: make sure the singleton workspace row exists."""

from __future__ import annotations

from ..db import session_scope
from ..models import Workspace


def ensure_workspace() -> None:
    with session_scope() as db:
        ws = db.get(Workspace, "default")
        if ws is None:
            db.add(Workspace(id="default"))
