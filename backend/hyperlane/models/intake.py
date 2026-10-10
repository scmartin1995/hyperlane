"""Email (or form) intake: a request arrives, the agent clarifies it, then it becomes backlog."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow
from ._base import IdMixin, TimestampMixin


class IntakeRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "intake_requests"

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | web | slack | chat
    requester_name: Mapped[str | None] = mapped_column(String(160))
    requester_email: Mapped[str | None] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    original_body: Mapped[str] = mapped_column(Text, nullable=False)
    thread_key: Mapped[str | None] = mapped_column(String(300), index=True)  # email Message-ID / References root
    state: Mapped[str] = mapped_column(String(20), default="new")
    # new -> clarifying -> ready -> converted | rejected | on_hold
    summary: Mapped[str | None] = mapped_column(Text)  # agent's understanding so far
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    # {problem, outcome, users, scope_in[], scope_out[], acceptance[], constraints[], priority, urgency,
    #  open_questions[], confidence 0..1, proposed_items[{type,title,description,points}]}
    questions_asked: Mapped[int] = mapped_column(default=0)
    max_questions: Mapped[int] = mapped_column(default=3)
    converted_item_ids: Mapped[list] = mapped_column(JSON, default=list)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"), index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)

    messages: Mapped[list[IntakeMessage]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="IntakeMessage.created_at"
    )


class IntakeMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "intake_messages"

    request_id: Mapped[str] = mapped_column(ForeignKey("intake_requests.id", ondelete="CASCADE"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound | outbound | internal
    author: Mapped[str] = mapped_column(String(160), nullable=False)  # email or "Hyperlane Agent" or user name
    body: Mapped[str] = mapped_column(Text, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(300))  # email Message-ID
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    request: Mapped[IntakeRequest] = relationship(back_populates="messages")
