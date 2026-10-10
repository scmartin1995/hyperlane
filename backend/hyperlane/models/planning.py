"""Capacity learning, sprint commitments and retrospectives."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._base import IdMixin, TimestampMixin


class CapacityEntry(Base, IdMixin, TimestampMixin):
    """What a person said they could do in a sprint, and what actually happened."""

    __tablename__ = "capacity_entries"
    __table_args__ = (UniqueConstraint("sprint_id", "user_id"),)

    sprint_id: Mapped[str] = mapped_column(ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    days_off: Mapped[float] = mapped_column(Float, default=0.0)
    available_hours: Mapped[float] = mapped_column(Float, default=0.0)
    planned_points: Mapped[float] = mapped_column(Float, default=0.0)
    planned_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_points: Mapped[float] = mapped_column(Float, default=0.0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class CapacityProfile(Base, IdMixin, TimestampMixin):
    """Learned per-person, per-project delivery profile (updated at every sprint close)."""

    __tablename__ = "capacity_profiles"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sprints_observed: Mapped[int] = mapped_column(Integer, default=0)
    avg_points: Mapped[float] = mapped_column(Float, default=0.0)  # exponentially weighted
    avg_count: Mapped[float] = mapped_column(Float, default=0.0)  # throughput (items / sprint)
    points_per_hour: Mapped[float] = mapped_column(Float, default=0.0)
    commitment_accuracy: Mapped[float] = mapped_column(Float, default=1.0)  # completed / planned
    stddev_points: Mapped[float] = mapped_column(Float, default=0.0)
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{sprint_id, planned, completed, hours}]
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1 grows with observations
    insights: Mapped[list] = mapped_column(JSON, default=list)  # agent-written notes, e.g. "over-commits by 20%"


class SprintCommitment(Base, IdMixin):
    """Snapshot of what was in a sprint at start (scope-change tracking, burndown baseline)."""

    __tablename__ = "sprint_commitments"

    sprint_id: Mapped[str] = mapped_column(ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, index=True)
    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    points: Mapped[float | None] = mapped_column(Float)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)
    added_mid_sprint: Mapped[bool] = mapped_column(Boolean, default=False)


class Retro(Base, IdMixin, TimestampMixin):
    __tablename__ = "retros"

    sprint_id: Mapped[str] = mapped_column(ForeignKey("sprints.id", ondelete="CASCADE"), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="open")  # open | closed
    went_well: Mapped[list] = mapped_column(JSON, default=list)  # [{id, text, author_id, votes}]
    improve: Mapped[list] = mapped_column(JSON, default=list)
    kudos: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)  # [{id, text, owner_id, done, action_item_id}]
    mood: Mapped[dict] = mapped_column(JSON, default=dict)  # {user_id: 1..5}
    agent_summary: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)  # frozen sprint stats at retro time
    facilitator_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    facilitator = relationship("User")
