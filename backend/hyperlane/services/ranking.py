"""Fractional ranking for backlog / board / sprint ordering.

Every work item carries one global `rank` (lower = higher up). Any list the UI shows (a backlog, a board
column, a sprint, the children of a parent) is a sub-sequence of that global order, so placing an item
between two of its neighbours in the *global* order also places it correctly in every sub-list.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import WorkItem

STEP = 1024.0  # gap between consecutive ranks after a renormalize / on append
MIN_GAP = 1e-6  # below this we renormalize before inserting

UNSET: Any = object()  # "argument not given" sentinel for scope filters


def rank_between(before: float | None, after: float | None) -> float:
    """Return a rank strictly between `before` (the item above) and `after` (the item below).

    Either side may be None (start / end of the list). Callers should check `needs_renormalize`
    first when both neighbours exist.
    """
    if before is None and after is None:
        return STEP
    if before is None:
        return after - STEP  # type: ignore[operator]
    if after is None:
        return before + STEP
    if after <= before:
        return before + STEP
    return before + (after - before) / 2.0


def needs_renormalize(before: float | None, after: float | None) -> bool:
    return before is not None and after is not None and (after - before) < MIN_GAP


def _scoped(stmt, project_id: str, *, parent_id: Any = UNSET, sprint_id: Any = UNSET, status: Any = UNSET):
    stmt = stmt.where(WorkItem.project_id == project_id, WorkItem.is_archived.is_(False))
    if parent_id is not UNSET:
        stmt = stmt.where(WorkItem.parent_id == parent_id)
    if sprint_id is not UNSET:
        stmt = stmt.where(WorkItem.sprint_id == sprint_id)
    if status is not UNSET:
        stmt = stmt.where(WorkItem.status == status)
    return stmt


def last_rank(
    db: Session,
    project_id: str,
    *,
    parent_id: Any = UNSET,
    sprint_id: Any = UNSET,
    status: Any = UNSET,
) -> float:
    """A rank that sorts after every item in the given scope (defaults to the whole project)."""
    stmt = _scoped(select(func.max(WorkItem.rank)), project_id, parent_id=parent_id, sprint_id=sprint_id, status=status)
    current = db.scalar(stmt)
    return STEP if current is None else float(current) + STEP


def first_rank(db: Session, project_id: str) -> float:
    current = db.scalar(select(func.min(WorkItem.rank)).where(WorkItem.project_id == project_id))
    return STEP if current is None else float(current) - STEP


def neighbours(
    db: Session, item: WorkItem, *, exclude_id: str | None = None
) -> tuple[WorkItem | None, WorkItem | None]:
    """The items directly above and below `item` in the project's global order (`exclude_id` is skipped)."""
    base = select(WorkItem).where(
        WorkItem.project_id == item.project_id, WorkItem.is_archived.is_(False), WorkItem.id != item.id
    )
    if exclude_id:
        base = base.where(WorkItem.id != exclude_id)
    above = db.scalars(
        base.where((WorkItem.rank < item.rank) | ((WorkItem.rank == item.rank) & (WorkItem.id < item.id)))
        .order_by(WorkItem.rank.desc(), WorkItem.id.desc())
        .limit(1)
    ).first()
    below = db.scalars(
        base.where((WorkItem.rank > item.rank) | ((WorkItem.rank == item.rank) & (WorkItem.id > item.id)))
        .order_by(WorkItem.rank.asc(), WorkItem.id.asc())
        .limit(1)
    ).first()
    return above, below


def renormalize(db: Session, project_id: str) -> int:
    """Rewrite all ranks in a project as STEP, 2*STEP, ... preserving the current order. Returns count."""
    items = list(
        db.scalars(select(WorkItem).where(WorkItem.project_id == project_id).order_by(WorkItem.rank, WorkItem.id))
    )
    for i, it in enumerate(items, start=1):
        it.rank = STEP * i
    db.flush()
    return len(items)
