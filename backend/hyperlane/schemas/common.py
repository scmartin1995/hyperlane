from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: str
    name: str
    handle: str
    email: str | None = None
    role: str
    emoji: str
    color: str
    skills: list = []
    bio: str | None = None
    slack_user_id: str | None = None
    timezone: str
    hours_per_week: float
    focus_factor: float
    is_active: bool
    preferences: dict = {}
    has_pin: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime


class UserBrief(ORM):
    id: str
    name: str
    handle: str
    emoji: str
    color: str
    role: str


class WorkspaceOut(ORM):
    id: str
    name: str
    tagline: str
    onboarded: bool
    theme: str
    flavor: bool
    settings: dict = {}


class LabelOut(ORM):
    id: str
    project_id: str
    name: str
    color: str


class ProjectOut(ORM):
    id: str
    key: str
    name: str
    description: str | None = None
    template: str
    methodology: str
    status: str
    color: str
    icon: str
    item_types: list = []
    workflow: list = []
    settings: dict = {}
    evm: dict = {}
    lead_id: str | None = None
    slack_channel: str | None = None
    created_at: datetime
    updated_at: datetime


class SprintOut(ORM):
    id: str
    project_id: str
    number: int
    name: str
    goal: str | None = None
    start_date: date
    end_date: date
    state: str
    committed_points: float
    committed_count: int
    completed_points: float
    completed_count: int
    capacity_points: float | None = None
    capacity_hours: float | None = None
    planning_notes: dict = {}
    closed_at: datetime | None = None


class CommentOut(ORM):
    id: str
    work_item_id: str
    author_id: str | None = None
    author_name: str | None = None
    author: UserBrief | None = None
    body: str
    source: str
    external_ref: str | None = None
    is_decision: bool
    created_at: datetime
    edited_at: datetime | None = None


class WorkItemOut(ORM):
    id: str
    project_id: str
    number: int
    key: str = ""  # "HL-12", filled by the API
    type: str
    parent_id: str | None = None
    title: str
    description: str | None = None
    acceptance_criteria: str | None = None
    status: str
    priority: str
    points: float | None = None
    estimate_hours: float | None = None
    actual_hours: float | None = None
    actual_cost: float | None = None
    business_value: int | None = None
    rank: float
    assignee_id: str | None = None
    reporter_id: str | None = None
    sprint_id: str | None = None
    due_date: date | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source: str
    source_ref: str | None = None
    blocked: bool
    blocked_reason: str | None = None
    custom: dict = {}
    is_archived: bool
    labels: list[LabelOut] = []
    assignee: UserBrief | None = None
    comment_count: int = 0
    child_count: int = 0
    created_at: datetime
    updated_at: datetime


class ActivityOut(ORM):
    id: str
    project_id: str | None = None
    entity_type: str
    entity_id: str
    action: str
    actor_id: str | None = None
    actor_name: str | None = None
    summary: str
    changes: dict = {}
    at: datetime


# ---- integrations (owner: backend-integrations) ----


class NotificationLogOut(ORM):
    id: str
    channel: str
    target: str | None = None
    kind: str
    entity_type: str | None = None
    entity_id: str | None = None
    body: str
    ok: bool
    error: str | None = None
    created_at: datetime


class StatusTransitionOut(ORM):
    id: str
    work_item_id: str
    from_status: str | None = None
    to_status: str
    from_category: str | None = None
    to_category: str
    actor_id: str | None = None
    at: datetime


class ActionItemOut(ORM):
    id: str
    owner_id: str
    title: str
    notes: str | None = None
    due_date: date | None = None
    done: bool
    done_at: datetime | None = None
    priority: str
    tags: list = []
    work_item_id: str | None = None
    project_id: str | None = None
    source: str
    source_ref: str | None = None
    snoozed_until: date | None = None
    position: float
    created_at: datetime
    updated_at: datetime


# ---- agent / chat / intake (owner: backend-agent; append-only) ----


class ChatMessageOut(ORM):
    id: str
    thread_id: str
    role: str
    content: str
    tool_calls: list = []
    usage: dict = {}
    created_at: datetime


class ChatThreadOut(ORM):
    id: str
    user_id: str
    project_id: str | None = None
    title: str
    mode: str
    context: dict = {}
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut] | None = None


class IntakeMessageOut(ORM):
    id: str
    request_id: str
    direction: str
    author: str
    body: str
    external_ref: str | None = None
    meta: dict = {}
    created_at: datetime


class IntakeRequestOut(ORM):
    work_item_id: str | None = None
    id: str
    project_id: str | None = None
    channel: str
    requester_name: str | None = None
    requester_email: str | None = None
    subject: str
    original_body: str
    state: str
    summary: str | None = None
    requirements: dict = {}
    questions_asked: int
    max_questions: int
    converted_item_ids: list = []
    owner_id: str | None = None
    last_activity_at: datetime
    needs_human: bool
    messages: list[IntakeMessageOut] = []
    created_at: datetime
    updated_at: datetime


class AgentStatusOut(BaseModel):
    provider: str
    model: str
    available: bool
    detail: str


class BacklogProposalItem(BaseModel):
    temp_id: str
    parent_temp_id: str | None = None
    type: str
    title: str
    description: str = ""
    acceptance_criteria: str | None = None
    points: float | None = None
    priority: str | None = "medium"
    labels: list[str] = []


class BacklogProposalOut(BaseModel):
    items: list[BacklogProposalItem]
    summary: str
    questions: list[str] = []


class ImportPreviewOut(BaseModel):
    file_token: str
    sheet: str
    sheets: list[str]
    columns: list[str]
    rows: list[dict]
    total_rows: int
    mapping: dict[str, str | None]
    notes: list[str] = []
