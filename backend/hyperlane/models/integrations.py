"""Outbound notification log (Slack / Teams / email) for auditability."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import IdMixin, TimestampMixin


class NotificationLog(Base, IdMixin, TimestampMixin):
    __tablename__ = "notification_log"

    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # slack | teams | email
    target: Mapped[str | None] = mapped_column(String(200))  # channel id / user id / email address
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # item_update | sprint_start | digest | intake_reply ...
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(String(120))  # slack ts
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
