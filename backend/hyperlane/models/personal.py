"""Private per-user action items and notes. Only the owner can read these."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import IdMixin, TimestampMixin


class ActionItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "action_items"

    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)  # markdown, private
    due_date: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | agent | slack | retro | chat
    source_ref: Mapped[str | None] = mapped_column(String(200))
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    position: Mapped[float] = mapped_column(default=0.0)
