"""Earned value snapshots (one per project per day, plus one per sprint close)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import IdMixin, TimestampMixin


class EvmSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "evm_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "as_of"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    sprint_id: Mapped[str | None] = mapped_column(ForeignKey("sprints.id", ondelete="SET NULL"))
    bac: Mapped[float] = mapped_column(Float, default=0.0)
    pv: Mapped[float] = mapped_column(Float, default=0.0)
    ev: Mapped[float] = mapped_column(Float, default=0.0)
    ac: Mapped[float] = mapped_column(Float, default=0.0)
    planned_points: Mapped[float] = mapped_column(Float, default=0.0)
    completed_points: Mapped[float] = mapped_column(Float, default=0.0)
    total_points: Mapped[float] = mapped_column(Float, default=0.0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # {sv, cv, spi, cpi, eac, etc, vac, tcpi, pct_complete, pct_planned}
    note: Mapped[str | None] = mapped_column(String(300))
