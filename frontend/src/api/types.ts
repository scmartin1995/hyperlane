// Shared API types. Keep in sync with backend/hyperlane/schemas and docs/API.md.

export type Id = string;

export interface UserBrief { id: Id; name: string; handle: string; emoji: string; color: string; role: string }
export interface User extends UserBrief {
  email: string | null; skills: string[]; bio: string | null; slack_user_id: string | null; timezone: string;
  hours_per_week: number; focus_factor: number; is_active: boolean; preferences: Record<string, unknown>;
  has_pin: boolean; last_seen_at: string | null; created_at: string;
}

export interface Workspace { id: Id; name: string; tagline: string; onboarded: boolean; theme: "dark" | "light" | "system"; flavor: boolean; settings: Record<string, unknown> }

export interface Health {
  ok: boolean; version: string; onboarded: boolean; profiles: number; projects: number;
  llm: { provider: string; model: string; configured: boolean }; slack: boolean; teams: boolean; email_intake: boolean;
}

export type StatusCategory = "todo" | "in_progress" | "done";
export interface ItemType { key: string; name: string; plural: string; icon: string; color: string; level: number }
export interface WorkflowState { key: string; name: string; category: StatusCategory; wip_limit: number | null; color: string }
export interface ProjectSettings {
  estimation: "points" | "hours" | "throughput"; points_scale: number[]; sprint_length_days: number;
  working_days: number[]; default_type: string; board_group_by: string; [k: string]: unknown;
}
export interface EvmConfig {
  enabled: boolean; currency: string; bac: number; cost_per_point: number; cost_per_hour: number;
  planned_points: number; planned_sprints: number; start_date: string | null; end_date: string | null;
  baseline_locked_at: string | null; method: "points" | "hours" | "count";
}
export interface Template { key: string; name: string; tagline: string; icon: string; methodology: string; item_types: ItemType[]; workflow: WorkflowState[]; settings: ProjectSettings }

export interface Project {
  id: Id; key: string; name: string; description: string | null; template: string; methodology: "scrum" | "kanban" | "hybrid";
  status: string; color: string; icon: string; item_types: ItemType[]; workflow: WorkflowState[]; settings: ProjectSettings; evm: EvmConfig;
  lead_id: Id | null; slack_channel: string | null; created_at: string; updated_at: string;
}
export interface ProjectSummary {
  project: Project; counts_by_status: Record<string, number>; counts_by_type: Record<string, number>;
  total_items: number; done_items: number; total_points: number; done_points: number;
  active_sprint: Sprint | null; next_sprint: Sprint | null; members: UserBrief[]; blocked: number; overdue: number;
}

export interface Label { id: Id; project_id: Id; name: string; color: string }
export type Priority = "critical" | "high" | "medium" | "low" | "none";

export interface WorkItem {
  id: Id; project_id: Id; number: number; key: string; type: string; parent_id: Id | null; title: string;
  description: string | null; acceptance_criteria: string | null; status: string; priority: Priority;
  points: number | null; estimate_hours: number | null; actual_hours: number | null; actual_cost: number | null;
  business_value: number | null; rank: number; assignee_id: Id | null; reporter_id: Id | null; sprint_id: Id | null;
  due_date: string | null; started_at: string | null; completed_at: string | null; source: string; source_ref: string | null;
  blocked: boolean; blocked_reason: string | null; custom: Record<string, unknown>; is_archived: boolean;
  labels: Label[]; assignee: UserBrief | null; comment_count: number; child_count: number; created_at: string; updated_at: string;
}
export interface WorkItemDetail extends WorkItem { children: WorkItem[]; comments: Comment[]; parent: WorkItem | null; sprint: Sprint | null }
export interface WorkItemTreeNode extends WorkItem { children: WorkItemTreeNode[] }

export interface WorkItemInput {
  title: string; type?: string; parent_id?: Id | null; description?: string | null; acceptance_criteria?: string | null;
  status?: string; priority?: Priority; points?: number | null; estimate_hours?: number | null; actual_hours?: number | null;
  business_value?: number | null; assignee_id?: Id | null; sprint_id?: Id | null; due_date?: string | null;
  labels?: string[]; blocked?: boolean; blocked_reason?: string | null; custom?: Record<string, unknown>; source?: string;
}
export interface MoveInput { status?: string; sprint_id?: Id | null; parent_id?: Id | null; before_id?: Id | null; after_id?: Id | null }

export interface Comment {
  id: Id; work_item_id: Id; author_id: Id | null; author_name: string | null; author: UserBrief | null; body: string;
  source: string; external_ref: string | null; is_decision: boolean; created_at: string; edited_at: string | null;
}

export interface Sprint {
  id: Id; project_id: Id; number: number; name: string; goal: string | null; start_date: string; end_date: string;
  state: "planned" | "active" | "closed"; committed_points: number; committed_count: number; completed_points: number;
  completed_count: number; capacity_points: number | null; capacity_hours: number | null; planning_notes: Record<string, unknown>; closed_at: string | null;
}

export interface Activity { id: Id; project_id: Id | null; entity_type: string; entity_id: Id; action: string; actor_id: Id | null; actor_name: string | null; summary: string; changes: Record<string, [unknown, unknown]>; at: string }
export interface StatusTransition { id: Id; work_item_id: Id; from_status: string | null; to_status: string; from_category: string | null; to_category: string; actor_id: Id | null; at: string }

export interface ActionItem {
  id: Id; owner_id: Id; title: string; notes: string | null; due_date: string | null; done: boolean; done_at: string | null;
  priority: Priority; tags: string[]; work_item_id: Id | null; project_id: Id | null; source: string; source_ref: string | null;
  snoozed_until: string | null; position: number; created_at: string; updated_at: string;
}

// ---- planning / capacity ----
export interface CapacityEntry { id: Id; sprint_id: Id; user_id: Id; days_off: number; available_hours: number; planned_points: number; planned_count: number; completed_points: number; completed_count: number; notes: string | null }
export interface CapacityProfile {
  id: Id; project_id: Id; user_id: Id; user?: UserBrief; sprints_observed: number; avg_points: number; avg_count: number; points_per_hour: number;
  commitment_accuracy: number; stddev_points: number; history: { sprint_id: Id; sprint_name?: string; planned: number; completed: number; hours: number }[];
  confidence: number; insights: string[];
}
export interface SprintCapacity { sprint: Sprint; entries: (CapacityEntry & { user: UserBrief; suggested_points: number; profile: CapacityProfile | null })[]; team_points: number; team_hours: number; team_count: number; method: "points" | "throughput" | "hours" }
export interface PlanSuggestion {
  sprint: Sprint; capacity: SprintCapacity; candidates: (WorkItem & { score: number; reason: string })[];
  recommended_ids: Id[]; recommended_points: number; confidence: number; notes: string[]; per_person: Record<Id, { points: number; items: Id[] }>;
}
export interface RetroEntry { id: string; text: string; author_id: Id | null; votes: number }
export interface RetroAction { id: string; text: string; owner_id: Id | null; done: boolean; action_item_id: Id | null }
export interface Retro {
  id: Id; sprint_id: Id; project_id: Id; state: "open" | "closed"; went_well: RetroEntry[]; improve: RetroEntry[]; kudos: RetroEntry[];
  actions: RetroAction[]; mood: Record<Id, number>; agent_summary: string | null; stats: Record<string, unknown>; facilitator_id: Id | null;
}

// ---- metrics / reports ----
export interface MetricsOverview {
  project_id: Id; as_of: string;
  velocity: { sprint: string; sprint_id: Id; committed: number; completed: number }[];
  avg_velocity: number; velocity_trend: number; throughput_per_week: number; avg_cycle_time_days: number; p85_cycle_time_days: number;
  wip: number; wip_limit_breaches: { status: string; count: number; limit: number }[]; flow_efficiency: number | null;
  blocked: number; overdue: number; active_sprint: { sprint: Sprint; pct_time: number; pct_scope_done: number; on_track: boolean; days_left: number } | null;
  health: { score: number; label: string; signals: { name: string; status: "good" | "warn" | "bad"; detail: string }[] };
}
export interface BurndownPoint { date: string; ideal: number; remaining: number; scope: number; done: number }
export interface CfdPoint { date: string; [status: string]: number | string }
export interface CycleTimeReport { points: { item_id: Id; key: string; title: string; type: string; completed_at: string; cycle_days: number; lead_days: number }[]; p50: number; p85: number; p95: number; avg: number; by_type: Record<string, number> }
export interface ThroughputReport { weeks: { week_start: string; count: number; points: number }[]; avg_count: number; avg_points: number }
export interface Forecast {
  mode: "how_many" | "when"; simulations: number; history_weeks: number; samples: number[];
  how_many?: { weeks: number; p50: number; p70: number; p85: number; p95: number; histogram: { value: number; count: number }[] };
  when?: { items: number; p50_date: string; p70_date: string; p85_date: string; p95_date: string; histogram: { date: string; count: number }[] };
  warning: string | null;
}
export interface EvmPoint { date: string; pv: number; ev: number; ac: number; sprint_id?: Id | null }
export interface EvmReport {
  config: EvmConfig; as_of: string; bac: number; pv: number; ev: number; ac: number; sv: number; cv: number; spi: number; cpi: number;
  eac: number; etc: number; vac: number; tcpi: number; pct_complete: number; pct_planned: number; pct_spent: number;
  forecast_end_date: string | null; series: EvmPoint[]; status: "on_track" | "at_risk" | "off_track" | "not_configured"; narrative: string;
}

// ---- intake ----
export interface IntakeMessage { id: Id; request_id: Id; direction: "inbound" | "outbound" | "internal"; author: string; body: string; external_ref: string | null; meta: Record<string, unknown>; created_at: string }
export interface IntakeRequirements {
  problem?: string; outcome?: string; users?: string; scope_in?: string[]; scope_out?: string[]; acceptance?: string[]; constraints?: string[];
  priority?: Priority; urgency?: string; open_questions?: string[]; confidence?: number;
  proposed_items?: { type: string; title: string; description?: string; points?: number | null; acceptance_criteria?: string }[];
}
export interface IntakeRequest {
  id: Id; project_id: Id | null; channel: string; requester_name: string | null; requester_email: string | null; subject: string; original_body: string;
  state: "new" | "clarifying" | "ready" | "converted" | "rejected" | "on_hold"; summary: string | null; requirements: IntakeRequirements;
  questions_asked: number; max_questions: number; converted_item_ids: Id[]; owner_id: Id | null; last_activity_at: string; needs_human: boolean;
  messages: IntakeMessage[]; created_at: string; updated_at: string;
}

// ---- chat / agent ----
export interface ChatThread { id: Id; user_id: Id; project_id: Id | null; title: string; mode: string; context: Record<string, unknown>; created_at: string; updated_at: string; messages?: ChatMessage[] }
export interface ChatMessage { id: Id; thread_id: Id; role: "user" | "assistant" | "tool"; content: string; tool_calls: { name: string; input: unknown; result_summary?: string }[]; usage: Record<string, number>; created_at: string }
// SSE stream events from POST /chat/threads/{id}/messages
export type ChatStreamEvent =
  | { type: "text"; delta: string }
  | { type: "tool_call"; name: string; input: unknown; id: string }
  | { type: "tool_result"; id: string; name: string; summary: string; ok: boolean }
  | { type: "message"; message: ChatMessage }
  | { type: "error"; error: string }
  | { type: "done" };

export interface BacklogProposal { items: { temp_id: string; parent_temp_id: string | null; type: string; title: string; description: string; acceptance_criteria?: string; points?: number | null; priority?: Priority; labels?: string[] }[]; summary: string; questions: string[] }
export interface ImportPreview { file_token: string; sheet: string; sheets: string[]; columns: string[]; rows: Record<string, unknown>[]; total_rows: number; mapping: Record<string, string | null>; notes: string[] }
export interface AgentStatus { provider: string; model: string; available: boolean; detail: string }

export interface IntegrationsStatus { slack: { enabled: boolean; connected: boolean; channel: string | null; detail: string }; teams: { enabled: boolean; detail: string }; email: { enabled: boolean; detail: string; last_poll: string | null } }
export interface NotificationLogEntry { id: Id; channel: string; target: string | null; kind: string; entity_type: string | null; entity_id: Id | null; body: string; ok: boolean; error: string | null; created_at: string }

export interface LiveEvent { type: string; project_id: Id | null; entity_type: string | null; entity_id: Id | null; actor_id: Id | null; data: Record<string, unknown>; at: string }
