"""Business-analyst agent chat threads (per user, optionally scoped to a project)."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._base import IdMixin, TimestampMixin


class ChatThread(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_threads"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    mode: Mapped[str] = mapped_column(String(30), default="analyst")  # analyst | backlog-builder | planning | retro
    context: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {sprint_id, work_item_id}
    provider_session: Mapped[str | None] = mapped_column(String(120))  # claude-code session id if used

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_messages"

    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown for display
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)  # [{name, input, result_summary}]
    raw: Mapped[dict | None] = mapped_column(JSON)  # provider payload for replay (content blocks)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")
