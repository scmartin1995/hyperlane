"""Demo league: "Galactic Racer" — 5 pilots, ~45 items, 3 closed sprints with real-looking history, 1 active.

Idempotent: if a project with that name exists it is returned untouched. Timestamps are backdated so the
cycle-time / CFD / velocity / burndown / EVM charts have something to show on first run.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import session_scope, utcnow
from ..models import (
    ActionItem,
    Activity,
    CapacityEntry,
    Comment,
    IntakeMessage,
    IntakeRequest,
    Label,
    Project,
    Sprint,
    SprintCommitment,
    StatusTransition,
    User,
    WorkItem,
    Workspace,
)
from ..schemas.common import ProjectOut, UserBrief
from . import ranking
from .events import bus
from .projects import create_project
from .users import unique_handle

# ---------------------------------------------------------------------------------------------- content

USERS: list[dict[str, Any]] = [
    {"name": "Nova Reyes", "role": "lead", "emoji": "🚀", "color": "#e4b963",
     "skills": ["architecture", "python", "react"], "email": "nova@galactic.example",
     "bio": "Crew chief. Keeps the hyperlane clear and the sprints honest."},
    {"name": "Kai Tanaka", "role": "developer", "emoji": "🛸", "color": "#27cfc3",
     "skills": ["react", "typescript", "webgl"], "email": "kai@galactic.example",
     "bio": "Front-end pilot. If it moves on screen, Kai tuned it."},
    {"name": "Priya Okafor", "role": "developer", "emoji": "🔥", "color": "#bc553c",
     "skills": ["python", "fastapi", "sqlalchemy", "infra"], "email": "priya@galactic.example",
     "bio": "Backend engineer. Netcode, servers, and the occasional 3am hotfix."},
    {"name": "Marco Lindqvist", "role": "qa", "emoji": "🧪", "color": "#67a671",
     "skills": ["playwright", "testing", "automation"], "email": "marco@galactic.example",
     "bio": "Finds the bug before the players do. Usually."},
    {"name": "Zara Chen", "role": "po", "emoji": "🎨", "color": "#6b3a8e",
     "skills": ["product", "ux", "figma"], "email": "zara@galactic.example",
     "bio": "Product owner. Decides what ships and argues for the players.", "hours_per_week": 32},
]  # fmt: skip

# leaf: (type, title, points, assignee idx, sprint no (0 = backlog), outcome, description, acceptance criteria)
# outcomes: closed sprints -> "done" | "carry" (finished early next sprint); active -> done/review/in_progress/ready;
# backlog -> "backlog" | "ready"
EPICS: list[dict[str, Any]] = [
    {
        "title": "Race core",
        "description": "The feel of driving: hover physics, tracks, laps. Everything else is decoration.",
        "features": [
            {
                "title": "Vehicle physics",
                "description": "Hover-car handling model: acceleration, drift, collisions.",
                "items": [
                    ("story", "Implement hover-car acceleration curve", 5, 1, 1, "done",
                     "Replace the linear throttle with a tuned curve so cars feel heavy at launch and light at top speed.",
                     "- 0→100 in 2.4s on the Nebula track\n- Curve editable from the tuning panel\n- No change to top speed"),
                    ("story", "Drift handling with lateral grip model", 8, 1, 1, "done",
                     "Add a lateral grip model so players can hold a drift through long corners without spinning out.",
                     "- Drift initiates on handbrake + steer\n- Counter-steer recovers within 0.5s\n- Works with gamepad and keyboard"),
                    ("story", "Collision damage and recovery", 5, 2, 1, "carry",
                     "Collisions reduce speed and shield; a reset places the car back on the track line.",
                     "- Shield drops by impact energy\n- Reset after 3s off-track\n- Damage visible on the HUD"),
                    ("bug", "Car clips through barrier at high speed", 3, 2, 1, "done",
                     "At >300 km/h the car tunnels through thin barriers on the Rift track.",
                     "- Continuous collision detection enabled for cars\n- Repro no longer passes on Rift"),
                    ("task", "Tune gravity constants per track", 2, 0, 1, "done",
                     "Low-gravity tracks need a separate gravity constant and jump arc.",
                     "- Per-track gravity in track metadata\n- Defaults preserved for existing tracks"),
                ],
            },
            {
                "title": "Track builder",
                "description": "Spline-based editor plus the runtime pieces: checkpoints and lap timing.",
                "items": [
                    ("story", "Spline track editor with live preview", 8, 1, 1, "done",
                     "Editors drag control points; the mesh regenerates in real time.",
                     "- Add/remove/move control points\n- Undo/redo\n- Preview updates under 50ms for 200 points"),
                    ("story", "Checkpoint system", 3, 2, 1, "done",
                     "Ordered checkpoints detect progress and prevent shortcut exploits.",
                     "- Missing a checkpoint invalidates the lap\n- Wrong-way warning after 2s"),
                    ("story", "Lap timing and split times", 3, 2, 2, "done",
                     "Per-sector split times with best-lap deltas on the HUD.",
                     "- Sector deltas shown in green/red\n- Best lap persisted per track per player"),
                    ("bug", "Lap counter double counts on tight hairpin", 2, 3, 2, "done",
                     "Crossing the start line twice in the hairpin on Comet Alley increments the lap twice.",
                     "- Start-line trigger requires a full checkpoint cycle\n- Regression test on Comet Alley"),
                ],
            },
        ],
    },
    {
        "title": "Multiplayer league",
        "description": "Race against humans. Lobbies, matchmaking, servers, and the leaderboards that fuel rivalries.",
        "features": [
            {
                "title": "Matchmaking",
                "description": "Create and join lobbies; match players of similar skill.",
                "items": [
                    ("story", "Lobby creation and invites", 5, 2, 2, "done",
                     "Players create a lobby, share an invite code, and pick a track together.",
                     "- 6-char invite codes\n- Host can kick\n- Lobby survives host refresh for 60s"),
                    ("story", "Skill-based matching", 8, 2, 2, "carry",
                     "Match players by a rolling rating so new pilots don't meet league veterans in race one.",
                     "- Rating widens search window every 10s\n- Max wait 90s then fill with bots"),
                    ("spike", "Netcode latency study", 3, 0, 2, "done",
                     "Measure rollback vs lockstep on a 120ms simulated link and recommend one.",
                     "- Written recommendation with numbers\n- Prototype branch for the chosen approach"),
                    ("task", "Provision game servers in two regions", 5, 2, 2, "done",
                     "Terraform the EU and US race servers with autoscaling.",
                     "- Servers come up from a clean apply\n- Health check endpoint wired to the lobby service"),
                ],
            },
            {
                "title": "Leaderboards",
                "description": "Global and friend rankings per track and per season.",
                "items": [
                    ("story", "Global leaderboard per track", 3, 1, 3, "done",
                     "Top 100 times per track with the player's own position pinned.",
                     "- Loads in under 300ms\n- Own row highlighted even outside top 100"),
                    ("story", "Season reset with archived standings", 2, 2, 3, "done",
                     "Seasons end monthly; previous standings stay browsable.",
                     "- Season switcher on the leaderboard\n- Reset is a scheduled job, not manual"),
                    ("bug", "Leaderboard ties sort wrong", 1, 3, 3, "done",
                     "Equal times are ordered by insert order instead of by date achieved.",
                     "- Ties ordered by earliest achievement\n- Unit test covers equal times"),
                    ("story", "Friends leaderboard", 3, 1, 3, "carry",
                     "Filter the leaderboard to friends only.",
                     "- Toggle persists\n- Empty state invites adding friends"),
                ],
            },
        ],
    },
    {
        "title": "Garage & customization",
        "description": "Make the car yours: liveries, decals, upgrades. The part players screenshot.",
        "features": [
            {
                "title": "Paint shop",
                "description": "Livery editor and decal uploads.",
                "items": [
                    ("story", "Livery editor with layers", 8, 1, 2, "done",
                     "Layered paint editor: base coat, stripes, decals, with live 3D preview.",
                     "- Up to 8 layers\n- Preview rotates with drag\n- Save/load per car"),
                    ("story", "Decal upload with moderation queue", 5, 2, 3, "done",
                     "Players upload PNG decals; uploads go through a moderation queue before going public.",
                     "- PNG up to 1MB\n- Queue visible to moderators\n- Rejected decals notify the player"),
                    ("bug", "Livery preview flickers on tab switch", 2, 1, 3, "done",
                     "Switching browser tabs and back causes the WebGL preview to flicker for a second.",
                     "- Context restored without flicker\n- Verified on Chrome and Firefox"),
                ],
            },
            {
                "title": "Upgrades",
                "description": "Engine, shields, boost: an upgrade tree with an economy that doesn't break.",
                "items": [
                    ("story", "Engine upgrade tree", 5, 1, 3, "done",
                     "Three-branch upgrade tree with prerequisites and preview of stat changes.",
                     "- Prereqs enforced\n- Stat deltas shown before purchase"),
                    ("story", "Upgrade economy balancing", 5, 4, 3, "done",
                     "Credits earned per race vs upgrade prices, tuned so a full tree takes about 20 races.",
                     "- Spreadsheet model checked in\n- No upgrade is a strictly dominant choice"),
                    ("story", "Upgrade purchase flow", 3, 1, 4, "done",
                     "Buy, confirm, and apply an upgrade with a satisfying animation.",
                     "- Confirmation step\n- Credits update live\n- Purchase is idempotent on double-click"),
                    ("task", "Upgrade icons set", 2, 4, 4, "review",
                     "24 icons for the upgrade tree in the HUD style.",
                     "- SVG, 24px grid\n- Dark and light variants"),
                ],
            },
        ],
    },
    {
        "title": "Launch readiness",
        "description": "What has to be true before the public beta: telemetry, onboarding, accessibility.",
        "features": [
            {
                "title": "Telemetry & observability",
                "description": "Know what's happening in production before Discord tells us.",
                "items": [
                    ("story", "Crash reporting pipeline", 3, 2, 4, "done",
                     "Client crashes upload a minidump and stack trace to the crash service.",
                     "- Crashes grouped by signature\n- PII scrubbed from reports"),
                    ("story", "Performance dashboard", 5, 2, 4, "in_progress",
                     "Frame time, server tick time and matchmaking wait on one dashboard.",
                     "- p50/p95 for each metric\n- Alert thresholds visible"),
                    ("task", "Alerting rules for race servers", 2, 2, 4, "ready",
                     "Page on server tick > 50ms for 5 minutes or lobby error rate > 2%.",
                     "- Rules in code\n- Test alert fired and acknowledged"),
                ],
            },
            {
                "title": "Onboarding & tutorial",
                "description": "First five minutes: from install to a first clean lap.",
                "items": [
                    ("story", "Tutorial track with guided laps", 5, 1, 4, "in_progress",
                     "A short track that teaches throttle, drift and boost with on-track prompts.",
                     "- Three guided laps\n- Skippable after the first\n- Completion unlocks the first livery"),
                    ("story", "Controls hint overlay", 2, 1, 4, "ready",
                     "Context-sensitive control hints that fade after first use.",
                     "- Shows gamepad or keyboard glyphs\n- Dismissed per hint"),
                    ("story", "First-run profile setup", 3, 4, 0, "ready",
                     "Pick a pilot name and emoji before the first race.",
                     "- Name uniqueness checked\n- Can be changed later in settings"),
                    ("bug", "Tutorial skips step 3 on gamepad", 1, 3, 0, "backlog",
                     "With a gamepad connected the boost tutorial step never triggers.",
                     "- Step 3 triggers on gamepad\n- Playwright test with a virtual gamepad"),
                    ("story", "Ghost replay of your best lap", 5, 1, 0, "ready",
                     "Render a translucent ghost car following the player's best recorded lap.",
                     "- Ghost toggled in settings\n- Replays within 50ms of recorded inputs"),
                    ("story", "Photo mode", 3, 2, 0, "ready",
                     "Pause, free camera, filters, save PNG to disk.",
                     "- Camera orbit + FOV\n- Watermark toggle"),
                    ("story", "Pit-stop mini game", 8, 0, 0, "backlog",
                     "Timed button sequence during pit stops that shortens the stop when nailed.",
                     "- Sequence randomised per stop\n- Perfect run saves 1.5s"),
                    ("story", "Weather: rain on Mos Ravel", 5, 1, 0, "backlog",
                     "Rain reduces grip and adds spray particles; forecast shown pre-race.",
                     "- Grip scalar 0.85 in rain\n- Spray only behind moving cars"),
                    ("story", "Daily challenge board", 3, 3, 0, "ready",
                     "One seeded challenge per day with a global-free local leaderboard.",
                     "- Seed from date\n- Local scores only"),
                    ("task", "Telemetry export to CSV", 2, 2, 0, "backlog",
                     "Export lap telemetry (speed, boost, inputs) for analysis.",
                     "- CSV opens in Excel\n- One row per 100ms"),
                    ("story", "Controller remapping UI", 5, 3, 0, "ready",
                     "Let players remap any action to any button or axis.",
                     "- Conflicts highlighted\n- Reset to defaults"),
                    ("bug", "Boost sound keeps playing after crash", 1, 0, 0, "ready",
                     "Audio source isn't stopped when the car resets.",
                     "- Boost loop stops on reset"),
                    ("story", "Split-screen two player", 13, 1, 0, "backlog",
                     "Local two-player with horizontal split and shared HUD.",
                     "- Stable 60fps on reference rig\n- Independent camera per player"),
                    ("story", "Track editor: place checkpoints", 8, 2, 0, "backlog",
                     "Drag checkpoints onto a track and validate lap closure.",
                     "- Invalid layouts flagged\n- Save/load JSON"),
                    ("spike", "Evaluate WebGPU renderer", 5, 2, 0, "backlog",
                     "Measure frame time of the current scene on WebGPU vs WebGL2.",
                     "- Numbers for 3 GPUs\n- Go/no-go recommendation"),
                    ("task", "Crash reporter opt-in dialog", 2, 4, 0, "ready",
                     "Ask once, store choice locally, never upload without consent.",
                     "- Dialog copy reviewed\n- Choice editable in settings"),
                    ("spike", "Accessibility review", 3, 4, 0, "backlog",
                     "Audit colour contrast, motion settings and remappable controls against WCAG 2.2 AA.",
                     "- Findings doc with severity\n- Follow-up stories created"),
                ],
            },
        ],
    },
]

COMMENTS: dict[str, list[tuple[int, str, bool]]] = {
    # item title -> [(author idx, body, is_decision)]
    "Drift handling with lateral grip model": [
        (1, "First pass is in. Drift feels floaty on Comet Alley, tightening the grip curve.", False),
        (4, "Played it for an hour: this is the feel we want. Ship it, tune later.", False),
        (0, "Decision: we keep the handbrake-initiated drift. No auto-drift mode for beta.", True),
    ],
    "Skill-based matching": [
        (2, "Rating model is Glicko-2 with a 90s max wait. Bots fill after that.", False),
        (0, "Decision: new accounts start at 1500 with high deviation so they settle quickly.", True),
        (3, "Tested with 12 simulated clients, wait times look sane. One flake in the bot-fill path.", False),
    ],
    "Livery editor with layers": [
        (1, "Layer reorder by drag is in. Blend modes are out of scope for now.", False),
        (4, "Can we get a 'duplicate layer' button? Players will ask for it on day one.", False),
    ],
    "Collision damage and recovery": [
        (2, "Shield math done, reset placement still snaps to the wrong spline point near junctions.", False),
        (0, "Carrying this into Sprint 2. @Priya Okafor pair with Kai on the spline lookup.", False),
    ],
    "Performance dashboard": [
        (2, "Grafana board is up for frame time. Server tick panel next.", False),
        (0, "Decision: dashboard lives in Grafana, not in-game. Players never see it.", True),
    ],
    "Tutorial track with guided laps": [
        (4, "Prompt copy drafted. Keep it to one line per prompt, the HUD gets busy.", False),
        (1, "@Marco Lindqvist can you try the guided laps with a gamepad once it's on the dev build?", False),
    ],
    "Netcode latency study": [
        (2, "Rollback wins on 120ms links. Lockstep stutters badly above 80ms.", False),
        (0, "Decision: rollback netcode. Prototype branch is `netcode/rollback`.", True),
    ],
    "Upgrade economy balancing": [
        (4, "Model says 22 races for a full tree with average placings. Close enough.", False),
    ],
}

ACTION_ITEMS: list[list[dict[str, Any]]] = [
    [  # Nova
        {"title": "Write Sprint 4 goal in the sprint page", "priority": "high", "due": 1, "tags": ["sprint"]},
        {"title": "1:1 with Kai about the WebGL flicker postmortem", "priority": "medium", "due": 3},
        {"title": "Review Priya's server autoscaling PR", "priority": "high", "due": -1, "tags": ["review"]},
        {"title": "Draft beta launch checklist", "priority": "medium", "due": 9, "tags": ["launch"]},
        {"title": "Book retro room for Sprint 3", "priority": "low", "done": True},
    ],
    [  # Kai
        {"title": "Profile tutorial track frame drops on integrated GPUs", "priority": "high", "due": 2, "tags": ["perf"]},
        {"title": "Reply to decal moderation thread", "priority": "low", "due": 0},
        {"title": "Add duplicate-layer button to livery editor", "priority": "medium", "tags": ["garage"]},
        {"title": "Update WebGL context-loss notes in the wiki", "priority": "low", "done": True},
    ],
    [  # Priya
        {"title": "Rotate race server credentials", "priority": "critical", "due": -2, "tags": ["infra", "security"]},
        {"title": "Finish server tick panel on the dashboard", "priority": "high", "due": 2},
        {"title": "Write runbook for lobby service restarts", "priority": "medium", "due": 6, "tags": ["ops"]},
        {"title": "Benchmark SQLite WAL vs rollback journal for telemetry", "priority": "low"},
    ],
    [  # Marco
        {"title": "Virtual gamepad fixture for Playwright", "priority": "high", "due": 4, "tags": ["testing"]},
        {"title": "Re-run hairpin lap counter regression on all tracks", "priority": "medium", "due": 1},
        {"title": "File the bot-fill flake with a repro", "priority": "medium", "done": True},
        {"title": "Try the guided laps with a gamepad", "priority": "medium", "due": 2},
    ],
    [  # Zara
        {"title": "Player interview: first-run profile setup", "priority": "high", "due": 3, "tags": ["research"]},
        {"title": "Prioritise accessibility spike for Sprint 5", "priority": "medium", "due": 8},
        {"title": "Update the beta roadmap slide", "priority": "low", "due": -3},
        {"title": "Decide on season length (monthly vs 6 weeks)", "priority": "high", "tags": ["decision"]},
        {"title": "Send upgrade economy model to the team", "priority": "low", "done": True},
    ],
]


# ---------------------------------------------------------------------------------------------- helpers


def _dt(d: date, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour=hour, minute=minute))


class _Seeder:
    def __init__(self, db: Session, project_name: str) -> None:
        self.db = db
        self.project_name = project_name
        self.rng = random.Random(42)
        self.now = utcnow()
        self.today = self.now.date()
        self.users: list[User] = []
        self.project: Project
        self.sprints: dict[int, Sprint] = {}
        self.items: list[WorkItem] = []
        self.by_title: dict[str, WorkItem] = {}
        self.rank = ranking.STEP
        self.commitments: dict[int, list[WorkItem]] = {1: [], 2: [], 3: [], 4: []}
        self.done_in: dict[int, list[WorkItem]] = {1: [], 2: [], 3: [], 4: []}

    # ---- primitives ----

    def _clamp(self, at: datetime) -> datetime:
        return min(at, self.now - timedelta(minutes=5))

    def _activity(self, entity_type: str, entity_id: str, action: str, summary: str, actor: User | None,
                  at: datetime, changes: dict | None = None) -> None:  # fmt: skip
        self.db.add(
            Activity(
                project_id=self.project.id, entity_type=entity_type, entity_id=entity_id, action=action,
                actor_id=actor.id if actor else None, actor_name=actor.name if actor else None,
                summary=summary[:400], changes=changes or {}, at=self._clamp(at),
            )
        )  # fmt: skip

    def _transition(self, item: WorkItem, frm: str | None, to: str, actor: User | None, at: datetime) -> None:
        cat = {"backlog": "todo", "ready": "todo", "in_progress": "in_progress", "review": "in_progress", "done": "done"}
        self.db.add(
            StatusTransition(
                work_item_id=item.id, project_id=self.project.id, from_status=frm, to_status=to,
                from_category=cat.get(frm) if frm else None, to_category=cat[to],
                actor_id=actor.id if actor else None, at=self._clamp(at),
            )
        )  # fmt: skip

    # ---- steps ----

    def users_step(self) -> None:
        existing = {u.email: u for u in self.db.scalars(select(User).where(User.email.is_not(None)))}
        for i, spec in enumerate(USERS):
            user = existing.get(spec["email"])
            if user is None:
                user = User(
                    name=spec["name"], handle=unique_handle(self.db, spec["name"]), email=spec["email"],
                    role=spec["role"], emoji=spec["emoji"], color=spec["color"], skills=spec["skills"],
                    bio=spec["bio"], hours_per_week=spec.get("hours_per_week", 40.0), focus_factor=0.7,
                    timezone="UTC", preferences={"slack_dm": i in (0, 2)},
                )  # fmt: skip
                user.created_at = user.updated_at = self._dt_ago(50, 9 + i)
                self.db.add(user)
            self.users.append(user)
        self.db.flush()

    def _dt_ago(self, days: float, hour: int = 10) -> datetime:
        return _dt(self.today - timedelta(days=days), hour)

    def project_step(self) -> None:
        lead = self.users[0]
        s1_start = self.today - timedelta(days=45)
        self.project = create_project(
            self.db,
            {
                "name": self.project_name, "key": "GR", "template": "software-scrum",
                "description": "Anti-gravity racing league. Hover cars, split-second drifts, and a community that "
                "will absolutely notice a 2ms input lag. Public beta is the finish line.",
                "icon": "🏁", "color": "#e4b963", "lead_id": lead.id,
                "settings": {"start_date": s1_start.isoformat(),
                             "target_end_date": (s1_start + timedelta(days=8 * 14 - 1)).isoformat()},
                "labels": ["physics", "netcode", "garage", "ui", "infra", "tech-debt", "beta-blocker"],
            },
            lead,
        )  # fmt: skip
        self.project.created_at = self.project.updated_at = self._dt_ago(48, 9)
        for row in self.db.scalars(select(Activity).where(Activity.entity_id == self.project.id)):
            row.at = self.project.created_at
        for s in (1, 2, 3, 4):
            start = s1_start + timedelta(days=14 * (s - 1))
            if s == 4:
                start = self.today - timedelta(days=3)
            end = start + timedelta(days=13)
            sprint = Sprint(
                project_id=self.project.id, number=s, name=f"Sprint {s}", start_date=start, end_date=end,
                state="active" if s == 4 else "closed",
                goal={
                    1: "A car you can drive and a track to drive it on.",
                    2: "Race a friend: lobbies, servers, and the first livery.",
                    3: "Rivalries: leaderboards and the upgrade tree.",
                    4: "Beta readiness: see production, teach new pilots.",
                }[s],
            )  # fmt: skip
            sprint.created_at = sprint.updated_at = _dt(start - timedelta(days=2), 15)
            self.db.add(sprint)
            self.sprints[s] = sprint
        self.db.flush()

    def _new_item(self, type_: str, title: str, parent: WorkItem | None, created: datetime, **kw: Any) -> WorkItem:
        item = WorkItem(
            project_id=self.project.id, number=self.project.next_item_number, type=type_, title=title,
            parent_id=parent.id if parent else None, rank=self.rank, status="backlog",
            reporter_id=self.users[4].id if type_ in ("story", "spike", "epic", "feature") else self.users[3].id,
            **kw,
        )  # fmt: skip
        self.project.next_item_number += 1
        self.rank += ranking.STEP
        item.created_at = item.updated_at = created
        self.db.add(item)
        self.db.flush()
        self.items.append(item)
        self.by_title[title] = item
        self._transition(item, None, "backlog", self.users[4], created)
        self._activity("work_item", item.id, "created", f"Created {type_} GR-{item.number}: {title}", self.users[4],
                       created)  # fmt: skip
        return item

    def items_step(self) -> None:
        labels = {lab.name: lab for lab in self.db.scalars(select(Label).where(Label.project_id == self.project.id))}
        label_for = {"Race core": "physics", "Multiplayer league": "netcode", "Garage & customization": "garage",
                     "Launch readiness": "beta-blocker"}  # fmt: skip
        for ei, epic_spec in enumerate(EPICS):
            epic = self._new_item("epic", epic_spec["title"], None, self._dt_ago(47, 9 + ei),
                                  description=epic_spec["description"], priority="high" if ei < 2 else "medium",
                                  business_value=90 - ei * 15, assignee_id=self.users[0].id)  # fmt: skip
            epic.labels = [labels[label_for[epic_spec["title"]]]]
            for fi, feat_spec in enumerate(epic_spec["features"]):
                feature = self._new_item("feature", feat_spec["title"], epic, self._dt_ago(46, 10 + fi),
                                         description=feat_spec["description"], priority="high" if ei < 2 else "medium",
                                         business_value=80 - ei * 10 - fi * 5,
                                         assignee_id=self.users[(ei + fi) % 5].id)  # fmt: skip
                feature.labels = [labels[label_for[epic_spec["title"]]]]
                for spec in feat_spec["items"]:
                    self._leaf(feature, spec, labels)
        self._rollup()

    def _leaf(self, feature: WorkItem, spec: tuple, labels: dict[str, Label]) -> None:
        type_, title, pts, who, sprint_no, outcome, desc, ac = spec
        rng = self.rng
        assignee = self.users[who]
        if sprint_no:
            sprint = self.sprints[sprint_no]
            start = sprint.start_date
            created = _dt(start - timedelta(days=rng.randint(3, 12)), rng.randint(9, 17), rng.choice((0, 15, 30, 45)))
        else:
            start = None
            created = self._dt_ago(rng.randint(2, 20), rng.randint(9, 17))
        created = max(created, self.project.created_at + timedelta(hours=1))
        priority = "critical" if type_ == "bug" and pts >= 3 else ("high" if pts >= 5 else "medium")
        item = self._new_item(type_, title, feature, created, points=float(pts), description=desc,
                              acceptance_criteria=ac, priority=priority, assignee_id=assignee.id,
                              business_value=rng.randint(30, 95))  # fmt: skip
        extra = {"bug": "tech-debt", "task": "infra", "spike": "tech-debt"}.get(type_)
        item.labels = list(feature.labels) + ([labels[extra]] if extra and labels.get(extra) else [])

        events: list[tuple[str, datetime, int | None]] = []  # (status, at, sprint number the item is in)
        final_sprint = sprint_no or None
        if sprint_no:
            events.append(("ready", _dt(start - timedelta(days=1), 14, rng.choice((0, 20, 40))), sprint_no))
            ip = _dt(start + timedelta(days=rng.randint(0, 4)), rng.randint(9, 14), rng.choice((5, 25, 50)))
            if outcome in ("done", "carry", "review", "in_progress"):
                events.append(("in_progress", ip, sprint_no))
            if outcome == "done":
                rv = ip + timedelta(days=rng.randint(1, 4), hours=rng.randint(0, 6))
                rv = min(rv, _dt(sprint.end_date - timedelta(days=1), 16))
                dn = rv + timedelta(hours=rng.randint(6, 40))
                dn = min(dn, _dt(sprint.end_date, 17, 30))
                events += [("review", rv, sprint_no), ("done", dn, sprint_no)]
            elif outcome == "carry":
                nxt = self.sprints[sprint_no + 1]
                rv = _dt(nxt.start_date + timedelta(days=rng.randint(0, 2)), 11, 10)
                dn = rv + timedelta(days=1, hours=rng.randint(1, 5))
                events += [("review", rv, sprint_no + 1), ("done", dn, sprint_no + 1)]
                final_sprint = sprint_no + 1
            elif outcome == "review":
                events.append(("review", ip + timedelta(days=1, hours=3), sprint_no))
        elif outcome == "ready":
            events.append(("ready", created + timedelta(days=1), None))

        # apply history (clamped to "now" so the active sprint never has events in the future)
        status, last_at = "backlog", created
        for st, at, _ in events:
            at = self._clamp(max(at, last_at + timedelta(minutes=10)))
            if at <= last_at:
                break
            self._transition(item, status, st, assignee, at)
            self._activity("work_item", item.id, "moved", f"GR-{item.number} moved from {status} to {st}", assignee, at,
                           {"status": [status, st]})  # fmt: skip
            if st == "in_progress" and item.started_at is None:
                item.started_at = at
            if st == "done":
                item.completed_at = at
            status, last_at = st, at
        item.status = status
        item.updated_at = last_at
        item.sprint_id = self.sprints[final_sprint].id if final_sprint else None
        if item.status == "done":
            item.actual_hours = round(pts * 5 * rng.uniform(0.75, 1.45), 1)

        # commitments: the original sprint (and the next one when carried)
        if sprint_no:
            self.commitments[sprint_no].append(item)
            self.db.add(SprintCommitment(sprint_id=self.sprints[sprint_no].id, work_item_id=item.id, points=float(pts),
                                         added_at=_dt(start, 9)))  # fmt: skip
            if final_sprint and final_sprint != sprint_no:
                self.commitments[final_sprint].append(item)
                self.db.add(SprintCommitment(sprint_id=self.sprints[final_sprint].id, work_item_id=item.id,
                                             points=float(pts), added_at=_dt(self.sprints[final_sprint].start_date, 9)))  # fmt: skip
            if item.status == "done" and final_sprint:
                self.done_in[final_sprint].append(item)

    def _rollup(self) -> None:
        """Features/epics take their status + timestamps from their children."""
        lead = self.users[0]
        for parent in [i for i in self.items if i.type == "feature"] + [i for i in self.items if i.type == "epic"]:
            kids = [i for i in self.items if i.parent_id == parent.id]
            if not kids:
                continue
            started = [k.started_at for k in kids if k.started_at]
            if not started:
                continue
            first = min(started)
            self._transition(parent, "backlog", "in_progress", lead, first)
            self._activity("work_item", parent.id, "moved", f"GR-{parent.number} moved from backlog to in_progress",
                           lead, first, {"status": ["backlog", "in_progress"]})  # fmt: skip
            parent.status, parent.started_at, parent.updated_at = "in_progress", first, first
            if all(k.status == "done" for k in kids):
                last = max(k.completed_at for k in kids if k.completed_at)
                self._transition(parent, "in_progress", "done", lead, last)
                self._activity("work_item", parent.id, "moved", f"GR-{parent.number} moved from in_progress to done",
                               lead, last, {"status": ["in_progress", "done"]})  # fmt: skip
                parent.status, parent.completed_at, parent.updated_at = "done", last, last

    def sprints_step(self) -> None:
        lead = self.users[0]
        for n, sprint in self.sprints.items():
            committed = self.commitments[n]
            sprint.committed_points = float(sum(i.points or 0 for i in committed))
            sprint.committed_count = len(committed)
            done = self.done_in[n]
            sprint.completed_points = float(sum(i.points or 0 for i in done)) if sprint.state == "closed" else 0.0
            sprint.completed_count = len(done) if sprint.state == "closed" else 0
            sprint.capacity_points = float(round(sum(u.hours_per_week for u in self.users) * 2 * 0.7 / 3.2))
            start_at = _dt(sprint.start_date, 9, 5)
            self._activity("sprint", sprint.id, "started",
                           f"{sprint.name} started with {sprint.committed_count} items / {sprint.committed_points:g} points",
                           lead, start_at)  # fmt: skip
            if sprint.state == "closed":
                sprint.closed_at = _dt(sprint.end_date, 17, 45)
                carried = [i for i in committed if i not in done]
                self._activity("sprint", sprint.id, "closed",
                               f"{sprint.name} closed: {sprint.completed_count}/{sprint.committed_count} items, "
                               f"{sprint.completed_points:g}/{sprint.committed_points:g} points; {len(carried)} carried",
                               lead, sprint.closed_at, {"carried": [None, [i.id for i in carried]]})  # fmt: skip
            # capacity entries (closed sprints get actuals; the active one gets the plan)
            per_user: dict[str, dict[str, float]] = {}
            for it in committed:
                if not it.assignee_id:
                    continue
                acc = per_user.setdefault(it.assignee_id, {"pp": 0.0, "pc": 0, "cp": 0.0, "cc": 0})
                acc["pp"] += it.points or 0
                acc["pc"] += 1
                if it in done:
                    acc["cp"] += it.points or 0
                    acc["cc"] += 1
            for user in self.users:
                acc = per_user.get(user.id, {"pp": 0.0, "pc": 0, "cp": 0.0, "cc": 0})
                days_off = self.rng.choice((0, 0, 0, 1, 2))
                available = round((user.hours_per_week * 2 - days_off * 8) * user.focus_factor, 1)
                self.db.add(
                    CapacityEntry(
                        sprint_id=sprint.id, user_id=user.id, days_off=float(days_off), available_hours=available,
                        planned_points=acc["pp"], planned_count=int(acc["pc"]),
                        completed_points=acc["cp"] if sprint.state == "closed" else 0.0,
                        completed_count=int(acc["cc"]) if sprint.state == "closed" else 0,
                        notes="Conference Thursday/Friday" if days_off == 2 else None,
                    )
                )  # fmt: skip
        self.db.flush()
        try:
            from .capacity import learn_from_sprint

            for sprint in self.sprints.values():
                if sprint.state == "closed":
                    learn_from_sprint(self.db, sprint)
        except ImportError:  # pragma: no cover
            pass
        self.db.flush()

    def evm_step(self) -> None:
        s1 = self.sprints[1]
        planned_points = float(sum(i.points or 0 for i in self.items))
        self.project.evm = {
            **self.project.evm,
            "enabled": True, "currency": "USD", "bac": 120000.0, "cost_per_point": 700.0, "cost_per_hour": 0.0,
            "planned_points": planned_points, "planned_sprints": 6, "method": "points",
            "start_date": s1.start_date.isoformat(),
            "end_date": (s1.start_date + timedelta(days=6 * 14 - 1)).isoformat(),
            "baseline_locked_at": _dt(s1.start_date, 9).isoformat(),
        }  # fmt: skip

    def comments_step(self) -> None:
        for title, entries in COMMENTS.items():
            item = self.by_title.get(title)
            if item is None:
                continue
            base = item.started_at or item.created_at
            end = item.completed_at or self.now
            span = max((end - base).total_seconds(), 3600)
            for k, (who, body, decision) in enumerate(entries):
                at = self._clamp(base + timedelta(seconds=span * (k + 1) / (len(entries) + 1)))
                author = self.users[who]
                c = Comment(work_item_id=item.id, author_id=author.id, author_name=author.name, body=body,
                            source="web", is_decision=decision)  # fmt: skip
                c.created_at = c.updated_at = at
                self.db.add(c)
                self.db.flush()
                self._activity("work_item", item.id, "commented",
                               f"{author.name} commented on GR-{item.number}" + (" (decision)" if decision else ""),
                               author, at, {"comment_id": [None, c.id]})  # fmt: skip

    def action_items_step(self) -> None:
        for user, specs in zip(self.users, ACTION_ITEMS, strict=True):
            linked = [i for i in self.items if i.assignee_id == user.id and i.status != "done"]
            for pos, spec in enumerate(specs, start=1):
                row = ActionItem(
                    owner_id=user.id, title=spec["title"], priority=spec.get("priority", "medium"),
                    tags=spec.get("tags", []), position=float(pos), project_id=self.project.id,
                    due_date=(self.today + timedelta(days=spec["due"])) if "due" in spec else None,
                    done=bool(spec.get("done")), source="manual",
                    work_item_id=linked[pos % len(linked)].id if linked and pos % 2 == 0 else None,
                )  # fmt: skip
                row.created_at = row.updated_at = self._dt_ago(self.rng.randint(1, 9), self.rng.randint(8, 18))
                if row.done:
                    row.done_at = row.created_at + timedelta(days=1)
                self.db.add(row)

    def intake_step(self) -> None:
        fresh = IntakeRequest(
            project_id=self.project.id, channel="email", requester_name="Lena Ortiz",
            requester_email="lena@fanmail.example", subject="Photo mode for race replays",
            original_body="Hi team! Love the beta. Could we get a photo mode in replays? Pause, free camera, "
            "hide the HUD, and export a 4K PNG. Half my Discord server would use it for wallpapers.",
            state="new", last_activity_at=self._dt_ago(1, 8), thread_key="<photo-mode-1@fanmail.example>",
        )  # fmt: skip
        fresh.created_at = fresh.updated_at = self._dt_ago(1, 8)
        self.db.add(fresh)
        self.db.flush()
        self.db.add(IntakeMessage(request_id=fresh.id, direction="inbound", author="lena@fanmail.example",
                                  body=fresh.original_body, external_ref=fresh.thread_key))  # fmt: skip

        clar = IntakeRequest(
            project_id=self.project.id, channel="email", requester_name="Tom Becker",
            requester_email="tom@steamdeckclub.example", subject="Controller support on Steam Deck",
            original_body="The game runs on Steam Deck but the right trigger doesn't throttle and the menus need a "
            "mouse. Can you add proper controller support? Lots of us play handheld.",
            state="clarifying", questions_asked=1, max_questions=3, owner_id=self.users[4].id,
            summary="Steam Deck players want full gamepad support: throttle on RT and gamepad-navigable menus.",
            requirements={
                "problem": "Right trigger does not throttle on Steam Deck; menus require a mouse.",
                "outcome": "Complete handheld play without touching the trackpads.",
                "users": "Steam Deck / handheld PC players",
                "scope_in": ["Map RT to throttle", "Gamepad navigation for all menus"],
                "scope_out": ["Gyro steering (separate request)"],
                "acceptance": ["Full race completed with gamepad only", "Settings menu navigable with d-pad"],
                "constraints": ["SteamInput must not override in-game bindings"],
                "priority": "high", "urgency": "before public beta",
                "open_questions": ["Is the issue present with SteamInput disabled?"],
                "confidence": 0.62,
                "proposed_items": [
                    {"type": "story", "title": "Gamepad navigation for all menus", "points": 5},
                    {"type": "bug", "title": "Right trigger not mapped to throttle on Steam Deck", "points": 2},
                ],
            },
            last_activity_at=self._dt_ago(3, 10), thread_key="<deck-controls-7@steamdeckclub.example>",
        )  # fmt: skip
        clar.created_at = clar.updated_at = self._dt_ago(5, 9)
        self.db.add(clar)
        self.db.flush()
        thread = [
            ("inbound", "tom@steamdeckclub.example", clar.original_body, self._dt_ago(5, 9)),
            ("outbound", "Hyperlane Agent",
             ("Thanks Tom! Quick one so we fix the right thing: does the right trigger work when SteamInput is "
             "disabled for the game (Properties → Controller → Disable Steam Input)? And which menus block you most?"),
             self._dt_ago(5, 10)),
            ("inbound", "tom@steamdeckclub.example",
             ("With SteamInput disabled RT works, so it's the SteamInput mapping. Garage and settings menus are the "
             "worst, the race menu is fine."), self._dt_ago(3, 10)),
        ]
        for direction, author, body, at in thread:
            m = IntakeMessage(request_id=clar.id, direction=direction, author=author, body=body)
            m.created_at = m.updated_at = at
            self.db.add(m)

    def finish(self) -> dict[str, Any]:
        ws = self.db.get(Workspace, "default")
        if ws is None:
            ws = Workspace(id="default")
            self.db.add(ws)
        ws.onboarded = True
        self.db.commit()
        return _result(self.db, self.project, created=True)


def _result(db: Session, project: Project, *, created: bool) -> dict[str, Any]:
    users = list(db.scalars(select(User).where(User.email.in_([u["email"] for u in USERS])).order_by(User.created_at)))
    items = db.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.project_id == project.id)) or 0
    sprints = db.scalar(select(func.count()).select_from(Sprint).where(Sprint.project_id == project.id)) or 0
    return {
        "created": created,
        "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        "users": [UserBrief.model_validate(u).model_dump(mode="json") for u in users],
        "items": int(items),
        "sprints": int(sprints),
    }


def seed(project_name: str = "Galactic Racer", db: Session | None = None) -> dict[str, Any]:
    """Create the demo league (idempotent by project name). Pass `db` to reuse a request session."""
    if db is None:
        with session_scope() as own:
            return seed(project_name, db=own)
    existing = db.scalar(select(Project).where(Project.name == project_name))
    if existing is not None:
        return _result(db, existing, created=False)
    s = _Seeder(db, project_name)
    s.users_step()
    s.project_step()
    s.items_step()
    s.sprints_step()
    s.evm_step()
    s.comments_step()
    s.action_items_step()
    s.intake_step()
    result = s.finish()
    bus.emit("project.updated", project_id=s.project.id, entity_type="project", entity_id=s.project.id,
             data={"seeded": True})  # fmt: skip
    bus.emit("workspace.updated", entity_type="workspace", entity_id="default")
    return result
