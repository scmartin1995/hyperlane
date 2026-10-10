"""Input models for the core routers (users, projects, items, sprints, action items)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from .common import WorkItemOut


class UserIn(BaseModel):
    name: str
    handle: str | None = None
    email: str | None = None
    role: str | None = None
    emoji: str | None = None
    color: str | None = None
    skills: list[str] | None = None
    hours_per_week: float | None = None
    focus_factor: float | None = None
    timezone: str | None = None
    slack_user_id: str | None = None
    bio: str | None = None
    preferences: dict[str, Any] | None = None


class UserPatch(UserIn):
    name: str | None = None
    is_active: bool | None = None


class ProjectIn(BaseModel):
    name: str
    key: str | None = None
    template: str = "software-scrum"
    methodology: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    lead_id: str | None = None
    item_types: list[dict[str, Any]] | None = None
    workflow: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None
    evm: dict[str, Any] | None = None
    labels: list[str] | None = None
    slack_channel: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    key: str | None = None
    methodology: str | None = None
    description: str | None = None
    status: str | None = None
    color: str | None = None
    icon: str | None = None
    lead_id: str | None = None
    item_types: list[dict[str, Any]] | None = None
    workflow: list[dict[str, Any]] | None = None
    workflow_rename: dict[str, str] | None = None
    settings: dict[str, Any] | None = None
    evm: dict[str, Any] | None = None
    slack_channel: str | None = None
    teams_webhook_override: str | None = None


class LabelIn(BaseModel):
    name: str
    color: str | None = None


class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None


class WorkItemPatch(BaseModel):
    """Partial `WorkItemInput` (types.ts). Only fields that were sent are applied."""

    title: str | None = None
    type: str | None = None
    parent_id: str | None = None
    description: str | None = None
    acceptance_criteria: str | None = None
    status: str | None = None
    priority: str | None = None
    points: float | None = None
    estimate_hours: float | None = None
    actual_hours: float | None = None
    actual_cost: float | None = None
    business_value: int | None = None
    assignee_id: str | None = None
    sprint_id: str | None = None
    due_date: date | None = None
    labels: list[str] | None = None
    blocked: bool | None = None
    blocked_reason: str | None = None
    custom: dict[str, Any] | None = None
    source: str | None = None
    source_ref: str | None = None


class WorkItemIn(WorkItemPatch):
    title: str


class BulkWorkItemIn(WorkItemIn):
    temp_id: str | None = None
    parent_temp_id: str | None = None


class BulkCreateIn(BaseModel):
    items: list[BulkWorkItemIn]


class BulkUpdateIn(BaseModel):
    ids: list[str]
    patch: WorkItemPatch


class MoveIn(BaseModel):
    status: str | None = None
    sprint_id: str | None = None
    parent_id: str | None = None
    before_id: str | None = None
    after_id: str | None = None


class MoveOut(WorkItemOut):
    wip_warning: str | None = None


class CommentIn(BaseModel):
    body: str
    is_decision: bool = False


class CommentPatch(BaseModel):
    body: str | None = None
    is_decision: bool | None = None


class SprintIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity_points: float | None = None
    capacity_hours: float | None = None
    planning_notes: dict[str, Any] | None = None


class SprintCloseIn(BaseModel):
    carry_over: str = "next"  # "next" | "backlog" | sprint id


class ActionItemIn(BaseModel):
    title: str
    notes: str | None = None
    due_date: date | None = None
    priority: str | None = None
    tags: list[str] | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    source: str | None = None
    source_ref: str | None = None
    snoozed_until: date | None = None
    done: bool | None = None


class ActionItemPatch(ActionItemIn):
    title: str | None = None
    position: float | None = None


class ReorderIn(BaseModel):
    ids: list[str] = Field(default_factory=list)


class SeedIn(BaseModel):
    project_name: str = "Atlas Customer Portal"
