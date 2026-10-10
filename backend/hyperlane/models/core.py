"""Core domain: workspace, projects, people, work items, sprints, discussion, activity."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow
from ._base import IdMixin, TimestampMixin


class Workspace(Base, IdMixin, TimestampMixin):
    """Singleton row (id='default'). Holds global, non-secret settings and onboarding state."""

    __tablename__ = "workspace"

    name: Mapped[str] = mapped_column(String(120), default="Hyperlane")
    tagline: Mapped[str] = mapped_column(String(200), default="No prophecy. Just skill, strategy, and the will to ship.")
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(20), default="dark")  # dark | light | system
    flavor: Mapped[bool] = mapped_column(Boolean, default=True)  # racing-flavored copy on/off
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # misc non-secret settings


class User(Base, IdMixin, TimestampMixin):
    """A dev profile. No passwords by default; optional PIN for private data (action items)."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    handle: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    role: Mapped[str] = mapped_column(String(60), default="developer")  # developer | pm | po | designer | qa | lead | stakeholder
    emoji: Mapped[str] = mapped_column(String(16), default="🚀")
    color: Mapped[str] = mapped_column(String(16), default="#27cfc3")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    bio: Mapped[str | None] = mapped_column(Text)
    slack_user_id: Mapped[str | None] = mapped_column(String(40))
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    hours_per_week: Mapped[float] = mapped_column(Float, default=40.0)
    focus_factor: Mapped[float] = mapped_column(Float, default=0.7)  # share of hours that becomes delivery
    pin_hash: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)  # notification prefs, UI prefs
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class Project(Base, IdMixin, TimestampMixin):
    """A project. Its template decides item types, workflow states and estimation mode.

    item_types: [{key, name, plural, icon, color, level}]  level 0 = top (epic), higher = finer
    workflow:   [{key, name, category: todo|in_progress|done, wip_limit: int|null, color}]
    settings:   {estimation: points|hours|throughput, sprint_length_days, points_scale: [..],
                 working_days: [0..4], start_date, target_end_date, ...}
    evm:        {enabled, bac (budget at completion, currency), currency, cost_per_point, cost_per_hour,
                 planned_points, planned_sprints, start_date, end_date, baseline_locked_at}
    """

    __tablename__ = "projects"

    key: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # e.g. HL -> HL-123
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(40), default="software-scrum")
    methodology: Mapped[str] = mapped_column(String(20), default="scrum")  # scrum | kanban | hybrid
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | done | archived
    color: Mapped[str] = mapped_column(String(16), default="#e4b963")
    icon: Mapped[str] = mapped_column(String(16), default="🏁")
    item_types: Mapped[list] = mapped_column(JSON, default=list)
    workflow: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    evm: Mapped[dict] = mapped_column(JSON, default=dict)
    next_item_number: Mapped[int] = mapped_column(Integer, default=1)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    slack_channel: Mapped[str | None] = mapped_column(String(80))
    teams_webhook_override: Mapped[str | None] = mapped_column(String(400))

    lead: Mapped[User | None] = relationship(foreign_keys=[lead_id])
    sprints: Mapped[list[Sprint]] = relationship(back_populates="project", cascade="all, delete-orphan")
    items: Mapped[list[WorkItem]] = relationship(back_populates="project", cascade="all, delete-orphan")


work_item_labels = Table(
    "work_item_labels",
    Base.metadata,
    Column("work_item_id", ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class Label(Base, IdMixin):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#6b3a8e")


class Sprint(Base, IdMixin, TimestampMixin):
    __tablename__ = "sprints"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="planned")  # planned | active | closed
    committed_points: Mapped[float] = mapped_column(Float, default=0.0)
    committed_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_points: Mapped[float] = mapped_column(Float, default=0.0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    capacity_points: Mapped[float | None] = mapped_column(Float)  # team capacity at planning time
    capacity_hours: Mapped[float | None] = mapped_column(Float)
    planning_notes: Mapped[dict] = mapped_column(JSON, default=dict)  # agent suggestions, confidence, etc.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped[Project] = relationship(back_populates="sprints")
    items: Mapped[list[WorkItem]] = relationship(back_populates="sprint")


class WorkItem(Base, IdMixin, TimestampMixin):
    """Any backlog item: epic, feature, story, task, bug... (types come from the project)."""

    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # display key = f"{project.key}-{number}"
    type: Mapped[str] = mapped_column(String(30), nullable=False, default="story")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)  # markdown
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)  # markdown
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # critical | high | medium | low | none
    points: Mapped[float | None] = mapped_column(Float)
    estimate_hours: Mapped[float | None] = mapped_column(Float)
    actual_hours: Mapped[float | None] = mapped_column(Float)  # for EVM actual cost (hours * rate)
    actual_cost: Mapped[float | None] = mapped_column(Float)  # explicit AC override (currency)
    business_value: Mapped[int | None] = mapped_column(Integer)  # 1..100
    rank: Mapped[float] = mapped_column(Float, default=0.0)  # backlog ordering (lower = higher)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reporter_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sprint_id: Mapped[str | None] = mapped_column(ForeignKey("sprints.id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | agent | email | excel | slack
    source_ref: Mapped[str | None] = mapped_column(String(120))  # intake request id, row number, slack ts
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSON, default=dict)  # template-specific fields
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="items")
    sprint: Mapped[Sprint | None] = relationship(back_populates="items")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    reporter: Mapped[User | None] = relationship(foreign_keys=[reporter_id])
    parent: Mapped[WorkItem | None] = relationship(remote_side="WorkItem.id", back_populates="children")
    children: Mapped[list[WorkItem]] = relationship(back_populates="parent")
    labels: Mapped[list[Label]] = relationship(secondary=work_item_labels)
    comments: Mapped[list[Comment]] = relationship(back_populates="item", cascade="all, delete-orphan")


class Comment(Base, IdMixin, TimestampMixin):
    """Discussion on a work item. Mirrors to/from Slack threads when configured."""

    __tablename__ = "comments"

    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str | None] = mapped_column(String(120))  # for agent / external authors
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    source: Mapped[str] = mapped_column(String(20), default="web")  # web | slack | agent | email | teams
    external_ref: Mapped[str | None] = mapped_column(String(120))  # slack ts, email message-id
    is_decision: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)

    item: Mapped[WorkItem] = relationship(back_populates="comments")
    author: Mapped[User | None] = relationship()


class StatusTransition(Base, IdMixin):
    """Every status change, for cycle time, lead time and cumulative flow."""

    __tablename__ = "status_transitions"

    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    from_category: Mapped[str | None] = mapped_column(String(20))
    to_category: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class Activity(Base, IdMixin):
    """Audit/event log for everything (feeds the activity feed and Slack notifications)."""

    __tablename__ = "activity"

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # work_item | sprint | project | comment | ...
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # created | updated | moved | commented | ...
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str | None] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)  # {field: [old, new]}
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
