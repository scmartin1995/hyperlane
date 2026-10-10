# Hyperlane API contract (v0.1)

All endpoints live under `/api`. JSON in/out. Identity comes from the `hl_session` cookie
(set by `POST /api/auth/login`). `CurrentUser` dependency = 401 if no profile picked.
Every mutation publishes an event on `services.events.bus` (see **Events**) and writes an `Activity` row
where it makes sense. TypeScript shapes for every response are in `frontend/src/api/types.ts`
(**that file is the source of truth for shapes; keep it and `backend/hyperlane/schemas/*` in sync**).

Conventions
- IDs are 12-char hex strings. Work item display key = `{project.key}-{number}` (e.g. `HL-42`), returned as `key`.
- Dates are ISO `YYYY-MM-DD`; datetimes are naive UTC ISO strings.
- List endpoints return plain arrays (no envelope) unless stated.
- Errors: `{detail: string}` with 400/403/404/409. `ValueError` raised in services → 400 automatically.
- Routers are auto-discovered: any module in `backend/hyperlane/api/` with a module-level `router: APIRouter` is mounted.
- Use `from ..services.auth import DB, CurrentUser, OptionalUser` for dependencies.

## Already implemented (foundation)
| Method | Path | Notes |
|---|---|---|
| GET | /health | `Health` |
| GET/PATCH | /workspace | `Workspace` |
| GET | /templates | `Template[]` |
| GET | /auth/profiles | `UserBrief[]` |
| POST | /auth/login | `{user_id, pin?}` → `User`, sets cookie |
| POST | /auth/logout | |
| GET | /auth/me | `User | null` |
| POST | /auth/pin | `{pin: string|null}` |
| GET | /events | SSE stream. Event name = event type, data = `LiveEvent` JSON |

## Core (owner: backend-core)
**Users**
- `GET /users` → `User[]` (active + inactive, `?active=true` filters)
- `POST /users` `{name, handle?, email?, role?, emoji?, color?, skills?, hours_per_week?, focus_factor?, timezone?, slack_user_id?, bio?}` → `User`. Handle auto-derived from name if missing. First user may be created without being logged in.
- `GET /users/{id}`, `PATCH /users/{id}` (any field above + `preferences`, `is_active`), `DELETE /users/{id}` (soft: is_active=false)

**Projects**
- `GET /projects` → `Project[]` (non-archived first)
- `POST /projects` `{name, key?, template, methodology?, description?, color?, icon?, lead_id?, item_types?, workflow?, settings?, evm?, labels?: string[], slack_channel?}` → `Project`. Applies template then overrides. Key auto-derived (uppercase initials, unique) when missing.
- `GET /projects/{id}` → `Project`; `PATCH /projects/{id}` (any field; `workflow`/`item_types` replace wholesale; renaming a workflow key must migrate items' statuses: accept `workflow_rename: {old_key: new_key}`); `DELETE /projects/{id}` → archives (status=archived).
- `GET /projects/{id}/summary` → `ProjectSummary`
- `GET /projects/{id}/labels` → `Label[]`; `POST /projects/{id}/labels` `{name, color?}`; `PATCH /labels/{id}`; `DELETE /labels/{id}`
- `GET /projects/{id}/activity?limit=50&entity_type=&entity_id=` → `Activity[]`

**Work items**
- `GET /projects/{pid}/items?type=&status=&category=&sprint_id=&assignee_id=&parent_id=&q=&label=&unscheduled=true&include_archived=false&include_done=true&limit=` → `WorkItem[]` ordered by `rank`. `sprint_id=none` means unscheduled.
- `GET /projects/{pid}/items/tree?include_done=true` → `WorkItemTreeNode[]` (roots = items with no parent, nested by parent_id, ordered by rank)
- `POST /projects/{pid}/items` `WorkItemInput` → `WorkItem`. Defaults: type=project.settings.default_type, status=first todo state, rank=last. `labels` = names (created if missing). Sets `reporter_id` to current user.
- `POST /projects/{pid}/items/bulk` `{items: WorkItemInput[]}` → `WorkItem[]` (used by excel import, agent backlog builder; supports `temp_id`/`parent_temp_id` to build hierarchies in one call)
- `GET /items/{id}` → `WorkItemDetail`
- `PATCH /items/{id}` partial `WorkItemInput` → `WorkItem`. Status changes write `StatusTransition`, set `started_at` on first in_progress, `completed_at` on done (cleared when leaving done). Emits `work_item.updated` with `data.changes`.
- `POST /items/{id}/move` `MoveInput` → `WorkItem`. Reorders using fractional ranks (`before_id`/`after_id` relative to siblings in the same list). Also used for board drag (status), sprint drag (sprint_id), hierarchy drag (parent_id). Enforces WIP limit? **No** – returns the item and includes `wip_warning: string|null` field in the response.
- `POST /items/bulk-update` `{ids: string[], patch: Partial<WorkItemInput>}` → `WorkItem[]`
- `DELETE /items/{id}` → archive (is_archived=true). `?hard=true` really deletes.
- `GET /items/{id}/activity` → `Activity[]`; `GET /items/{id}/transitions` → `StatusTransition[]`
- `POST /items/{id}/comments` `{body, is_decision?}` → `Comment` (source=web). `PATCH /comments/{id}` `{body?, is_decision?}`, `DELETE /comments/{id}`.
- `GET /search?q=&limit=20` → `WorkItem[]` across all projects (key match like `HL-12`, title/description contains)

**Sprints**
- `GET /projects/{pid}/sprints?state=` → `Sprint[]` (number desc)
- `POST /projects/{pid}/sprints` `{name?, goal?, start_date?, end_date?}` → `Sprint`. Defaults: number=next, name="Sprint N", start=day after last sprint end (or today), end=start+sprint_length_days-1.
- `GET /sprints/{id}` → `Sprint`; `PATCH /sprints/{id}`; `DELETE /sprints/{id}` (only planned; items go unscheduled)
- `GET /sprints/{id}/items` → `WorkItem[]`
- `POST /sprints/{id}/start` → `Sprint`. Only one active sprint per project. Snapshots `SprintCommitment` rows and `committed_points/count`; emits `sprint.started`.
- `POST /sprints/{id}/close` `{carry_over: "next" | "backlog" | sprint_id}` → `{sprint, carried: WorkItem[], completed: WorkItem[]}`. Writes `completed_points/count`, updates `CapacityEntry.completed_*` per assignee, calls `services.capacity.learn_from_sprint(sprint)` (owner: analytics; import lazily and tolerate ImportError), creates the next sprint if `carry_over=="next"` and none exists, emits `sprint.closed`.

**Private action items** (always scoped to `CurrentUser`; never readable by others)
- `GET /me/action-items?include_done=false` → `ActionItem[]` ordered by position, due
- `POST /me/action-items` `{title, notes?, due_date?, priority?, tags?, work_item_id?, project_id?, source?}` → `ActionItem`
- `PATCH /me/action-items/{id}`, `DELETE /me/action-items/{id}`, `POST /me/action-items/reorder` `{ids: string[]}`
- `GET /me/overview` → `{assigned: WorkItem[], in_progress: WorkItem[], action_items_open: number, action_items_overdue: number, mentions: Comment[], active_sprints: Sprint[]}`

**Demo data**
- `POST /dev/seed` `{project_name?}` → creates 5 users, 1 software-scrum project with ~45 items (epics/features/stories/bugs), 3 closed sprints with realistic transitions over the past 6 weeks + 1 active sprint, capacity entries, comments, some action items for every user, 2 intake requests. Idempotent-ish (returns existing if a project named "Atlas Customer Portal" exists). Used by the welcome flow's "Load the demo project" button.

## Analytics / planning (owner: backend-analytics) — `services/metrics.py`, `services/evm.py`, `services/forecast.py`, `services/capacity.py`, `api/reports.py`, `api/planning.py`
- `GET /projects/{pid}/metrics/overview` → `MetricsOverview`
- `GET /projects/{pid}/metrics/velocity?last=8` → `MetricsOverview["velocity"]`
- `GET /sprints/{id}/burndown` → `BurndownPoint[]` (daily, points or count based on project estimation; `scope` tracks scope changes)
- `GET /sprints/{id}/burnup` → `BurndownPoint[]`
- `GET /projects/{pid}/metrics/cfd?days=60` → `CfdPoint[]` (per workflow state, per day; built from StatusTransition)
- `GET /projects/{pid}/metrics/cycle-time?days=90` → `CycleTimeReport`
- `GET /projects/{pid}/metrics/throughput?weeks=12` → `ThroughputReport`
- `GET /projects/{pid}/forecast?mode=how_many&weeks=2` / `?mode=when&items=20` (`&sims=5000&history_weeks=12`) → `Forecast` (Monte Carlo over weekly throughput)
- `GET /projects/{pid}/evm` → `EvmReport`; `PUT /projects/{pid}/evm/config` `EvmConfig` (partial) → `Project`; `POST /projects/{pid}/evm/baseline` → locks baseline (planned_points from current scope, planned_sprints, dates) → `Project`; `POST /projects/{pid}/evm/snapshot` → `EvmSnapshot`; `GET /projects/{pid}/evm/snapshots` → `EvmSnapshot[]`. Daily snapshot job registered via `services.scheduler.register_job`.
- `GET /projects/{pid}/capacity` → `CapacityProfile[]` (with `user`)
- `GET /sprints/{id}/capacity` → `SprintCapacity`; `PUT /sprints/{id}/capacity` `{entries: {user_id, days_off, available_hours?, notes?}[]}` → `SprintCapacity`
- `GET /sprints/{id}/plan/suggest` → `PlanSuggestion` (ranks unscheduled ready items by priority/business value/rank/age, fills to capacity using learned profiles; works with points, throughput or hours)
- `POST /sprints/{id}/plan/commit` `{item_ids: string[]}` → `Sprint` (moves items into the sprint, records capacity planned_*)
- `GET /sprints/{id}/retro` → `Retro` (creates on first read); `PUT /sprints/{id}/retro` partial → `Retro`; `POST /sprints/{id}/retro/items` `{column: "went_well"|"improve"|"kudos"|"actions", text, owner_id?}`; `POST /sprints/{id}/retro/vote` `{column, entry_id}`; `POST /sprints/{id}/retro/mood` `{score 1..5}`; `POST /sprints/{id}/retro/generate` → agent summary (call `agent.summarize_retro(retro, stats)`; tolerate agent unavailable → heuristic summary); `POST /sprints/{id}/retro/close` → closes, creates private `ActionItem`s for action owners (source=retro).

## Agent (owner: backend-agent) — `agent/provider.py`, `agent/tools.py`, `agent/ba.py`, `agent/intake.py`, `agent/backlog.py`, `agent/importer.py`, `api/chat.py`, `api/intake.py`, `api/imports.py`
- `GET /agent/status` → `AgentStatus`
- `GET /chat/threads` → `ChatThread[]` (mine); `POST /chat/threads` `{project_id?, mode?, context?, title?}` → `ChatThread`; `GET /chat/threads/{id}` → `ChatThread` with `messages`; `DELETE /chat/threads/{id}`
- `POST /chat/threads/{id}/messages` `{content}` → **SSE stream** of `ChatStreamEvent` (`data:` JSON per event; types text/tool_call/tool_result/message/done/error). Persists user + assistant `ChatMessage`s.
- `POST /projects/{pid}/backlog/generate` `{prompt, parent_id?}` → `BacklogProposal` (agent drafts epics→features→stories with acceptance criteria and point guesses; asks `questions` when the prompt is thin). `POST /projects/{pid}/backlog/apply` `{items: BacklogProposal["items"], parent_id?}` → `WorkItem[]` (uses `/items/bulk` semantics).
- Intake: `GET /intake?state=` → `IntakeRequest[]`; `GET /intake/{id}`; `POST /intake` `{subject, body, requester_name?, requester_email?, project_id?, channel?}` → `IntakeRequest` then runs analyze; `POST /intake/{id}/messages` `{body, direction?: "inbound"|"internal", author?}` (a reply from the requester, or an internal note) → re-analyze if inbound; `POST /intake/{id}/analyze` → `IntakeRequest` (agent updates `summary`, `requirements`; if confidence < 0.75 and questions_asked < max → drafts ONE focused clarifying message (outbound) and sends it via `integrations.email.send_reply` if available, else just stores it; state=clarifying. Otherwise state=ready with `proposed_items`); `POST /intake/{id}/convert` `{project_id, parent_id?, items?}` → `WorkItem[]` (state=converted); `POST /intake/{id}/reject` `{reason?}`; `PATCH /intake/{id}` (`owner_id`, `project_id`, `state`, `max_questions`).
- Excel import: `POST /projects/{pid}/import/excel/preview` multipart `file` (+ optional `sheet`) → `ImportPreview` (columns, first 20 rows, heuristic mapping to item fields: title, type, description, status, priority, points, assignee, parent, labels, epic/feature names; agent refines mapping when available). `POST /projects/{pid}/import/excel/commit` `{file_token, sheet, mapping, create_missing_users?: bool}` → `{created: WorkItem[], skipped: number, warnings: string[]}`. Build hierarchy from a `parent`/`epic`/`feature` column when present. Store uploads under `data/uploads/`.
- Agent tools (callable by the BA agent): list/search items, get item, create item(s), update item, add comment, list sprints, get sprint summary/plan suggestion, list people & capacity, metrics overview, evm report, create private action item for current user, list my action items, propose backlog, send Slack message (if configured, only on explicit user ask), create intake request. Every tool executes inside `session_scope()` and emits events via the same services the API uses (import service functions from `services/items.py` etc. written by backend-core; coordinate by reading that code — do NOT duplicate business logic).
- Also export `agent.summarize_retro(retro, stats) -> str` and `agent.draft_capacity_insight(profile) -> list[str]` for analytics, and `agent.quick(prompt, system=None) -> str` for integrations.

## Integrations (owner: backend-integrations) — `integrations/__init__.py` (`start_all(app)`, `stop_all()`), `integrations/slack.py`, `integrations/teams.py`, `integrations/email.py`, `integrations/router.py`, `api/integrations.py`
- `GET /integrations/status` → `IntegrationsStatus`; `POST /integrations/test/slack` / `/teams` / `/email` → `{ok, detail}`; `GET /notifications/log?limit=50` → `NotificationLogEntry[]`; `POST /notifications/send` `{channel: "slack"|"teams", target?, text}`.
- Router subscribes to `bus` and sends: item status changes/assignments/comments (threaded per item when possible: keep slack `ts` in `NotificationLog.external_ref` keyed by entity_id), sprint start/close summaries, intake replies, daily digest (scheduler job, 09:00 local, per project: yesterday's done, today's WIP, blocked, overdue action items DM'd privately to each user who set `preferences.slack_dm=true`).
- Slack inbound (Socket Mode): thread replies on item messages → `Comment(source="slack")`; slash command `/hyperlane` with subcommands: `mine`, `HL-12 done|start|review`, `todo <text>` (private action item), `ask <question>` (BA agent quick answer), `standup`; app mentions → BA agent answer. Map Slack users to `User.slack_user_id` (fallback by email via `users.info`).
- Email: IMAP poll every `INTAKE_POLL_SECONDS` → new messages become `IntakeRequest` (dedupe by Message-ID; replies matched by `In-Reply-To`/`References` → `IntakeMessage(inbound)` then `agent.intake.analyze`). `send_reply(request, body)` via SMTP, threading headers set.
- Nothing is sent anywhere unless the corresponding env vars are set. All sends logged in `NotificationLog`.

## Events (`services/events.py`)
`bus.emit(type, project_id=, entity_type=, entity_id=, actor_id=, data={})`. Types used by the UI live in `frontend/src/lib/live.ts` (`known` list) — add new ones there too:
`work_item.created|updated|moved|deleted`, `comment.created|updated|deleted`, `sprint.created|updated|started|closed`, `project.created|updated|deleted`, `user.created|updated`, `action_item.created|updated|deleted`, `intake.created|updated`, `workspace.updated`, `evm.snapshot`, `capacity.updated`, `retro.updated`, `chat.message`, `notification.sent`.

## Triage (requests in the backlog) — `services/triage.py`, `api/triage.py`
Every `IntakeRequest` is mirrored into a `WorkItem` the moment it arrives (`triage.ensure_work_item`), in the project
named by `[KEY]` in the subject → `workspace.settings.intake_project_id` → first active project. The item carries
`custom.intake` (`IntakeMeta`), the label `needs-triage`, the request body + the assistant's findings in `description`,
and the clarification thread as comments (`external_ref = intake-msg:<id>`). `triage.sync_work_item` runs after every
analysis / reply.
- `GET /projects/{pid}/triage?include_snoozed=true` → `TriageItem[]` (open states: new, clarifying, ready, snoozed)
- `POST /items/{id}/triage` `{action: accept|escalate|decline|snooze, type?, sprint_id?, until?, reason?, create_children?}` → `{item, created}`.
  accept drops the label, optionally expands the assistant's proposed items as children (or adopts the first proposal's
  detail on leaf-level items) and marks the request converted; escalate = accept + move into the active sprint;
  decline archives the item and rejects the request; snooze hides it until a date (a 06:05 job wakes it).
- `POST /items/{id}/message-requester` `{body}` → sends by email when the connector is configured, always threads it.
- `PATCH /workspace {settings: {intake_project_id}}` sets the default project.
