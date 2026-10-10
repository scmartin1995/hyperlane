"""Project templates: what kinds of work items exist, the workflow, and estimation defaults.

A template is only a starting point; every field is editable per project afterwards.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CATEGORIES = ("todo", "in_progress", "done")

_SOFTWARE_TYPES = [
    {"key": "epic", "name": "Epic", "plural": "Epics", "icon": "🗺️", "color": "#6b3a8e", "level": 0},
    {"key": "feature", "name": "Feature", "plural": "Features", "icon": "🧩", "color": "#306376", "level": 1},
    {"key": "story", "name": "Story", "plural": "Stories", "icon": "📗", "color": "#27cfc3", "level": 2},
    {"key": "task", "name": "Task", "plural": "Tasks", "icon": "🔧", "color": "#e4b963", "level": 2},
    {"key": "bug", "name": "Bug", "plural": "Bugs", "icon": "🐛", "color": "#bc553c", "level": 2},
    {"key": "spike", "name": "Spike", "plural": "Spikes", "icon": "🔬", "color": "#c5c2c2", "level": 2},
]

_SCRUM_WORKFLOW = [
    {"key": "backlog", "name": "Backlog", "category": "todo", "wip_limit": None, "color": "#676767"},
    {"key": "ready", "name": "Ready", "category": "todo", "wip_limit": None, "color": "#c5c2c2"},
    {"key": "in_progress", "name": "In Progress", "category": "in_progress", "wip_limit": None, "color": "#27cfc3"},
    {"key": "review", "name": "In Review", "category": "in_progress", "wip_limit": None, "color": "#e4b963"},
    {"key": "done", "name": "Done", "category": "done", "wip_limit": None, "color": "#67a671"},
]

_KANBAN_WORKFLOW = [
    {"key": "backlog", "name": "Backlog", "category": "todo", "wip_limit": None, "color": "#676767"},
    {"key": "selected", "name": "Selected", "category": "todo", "wip_limit": 8, "color": "#c5c2c2"},
    {"key": "in_progress", "name": "In Progress", "category": "in_progress", "wip_limit": 4, "color": "#27cfc3"},
    {"key": "review", "name": "Review", "category": "in_progress", "wip_limit": 3, "color": "#e4b963"},
    {"key": "done", "name": "Done", "category": "done", "wip_limit": None, "color": "#67a671"},
]

TEMPLATES: dict[str, dict[str, Any]] = {
    "software-scrum": {
        "name": "Software · Scrum",
        "tagline": "Sprints, story points, velocity. Classic Scrum for software teams.",
        "icon": "📋",
        "methodology": "scrum",
        "item_types": _SOFTWARE_TYPES,
        "workflow": _SCRUM_WORKFLOW,
        "settings": {
            "estimation": "points",
            "points_scale": [1, 2, 3, 5, 8, 13, 21],
            "sprint_length_days": 14,
            "working_days": [0, 1, 2, 3, 4],
            "default_type": "story",
            "board_group_by": "none",
        },
        "labels": ["frontend", "backend", "infra", "ux", "tech-debt"],
    },
    "software-kanban": {
        "name": "Software · Kanban",
        "tagline": "Continuous flow, WIP limits, throughput forecasting.",
        "icon": "🌊",
        "methodology": "kanban",
        "item_types": _SOFTWARE_TYPES,
        "workflow": _KANBAN_WORKFLOW,
        "settings": {
            "estimation": "throughput",
            "points_scale": [1, 2, 3, 5, 8],
            "sprint_length_days": 14,
            "working_days": [0, 1, 2, 3, 4],
            "default_type": "story",
            "board_group_by": "none",
        },
        "labels": ["frontend", "backend", "support", "tech-debt"],
    },
    "product-discovery": {
        "name": "Product discovery",
        "tagline": "Opportunities, experiments, insights. Learn before you build.",
        "icon": "🧭",
        "methodology": "kanban",
        "item_types": [
            {"key": "outcome", "name": "Outcome", "plural": "Outcomes", "icon": "🎯", "color": "#6b3a8e", "level": 0},
            {"key": "opportunity", "name": "Opportunity", "plural": "Opportunities", "icon": "💡", "color": "#306376", "level": 1},
            {"key": "experiment", "name": "Experiment", "plural": "Experiments", "icon": "🧪", "color": "#27cfc3", "level": 2},
            {"key": "interview", "name": "Interview", "plural": "Interviews", "icon": "🎙️", "color": "#e4b963", "level": 2},
            {"key": "insight", "name": "Insight", "plural": "Insights", "icon": "🔭", "color": "#bc553c", "level": 2},
        ],
        "workflow": [
            {"key": "ideas", "name": "Ideas", "category": "todo", "wip_limit": None, "color": "#676767"},
            {"key": "planned", "name": "Planned", "category": "todo", "wip_limit": 6, "color": "#c5c2c2"},
            {"key": "running", "name": "Running", "category": "in_progress", "wip_limit": 3, "color": "#27cfc3"},
            {"key": "learned", "name": "Learned", "category": "done", "wip_limit": None, "color": "#67a671"},
        ],
        "settings": {"estimation": "throughput", "points_scale": [1, 2, 3, 5], "sprint_length_days": 14, "working_days": [0, 1, 2, 3, 4], "default_type": "experiment", "board_group_by": "none"},
        "labels": ["customer", "pricing", "onboarding", "retention"],
    },
    "marketing-campaign": {
        "name": "Marketing campaign",
        "tagline": "Campaigns, deliverables, launches. Ship the story.",
        "icon": "📣",
        "methodology": "hybrid",
        "item_types": [
            {"key": "campaign", "name": "Campaign", "plural": "Campaigns", "icon": "🚀", "color": "#6b3a8e", "level": 0},
            {"key": "initiative", "name": "Initiative", "plural": "Initiatives", "icon": "🧩", "color": "#306376", "level": 1},
            {"key": "deliverable", "name": "Deliverable", "plural": "Deliverables", "icon": "🎨", "color": "#27cfc3", "level": 2},
            {"key": "task", "name": "Task", "plural": "Tasks", "icon": "✅", "color": "#e4b963", "level": 2},
        ],
        "workflow": [
            {"key": "backlog", "name": "Backlog", "category": "todo", "wip_limit": None, "color": "#676767"},
            {"key": "drafting", "name": "Drafting", "category": "in_progress", "wip_limit": None, "color": "#27cfc3"},
            {"key": "approval", "name": "Approval", "category": "in_progress", "wip_limit": None, "color": "#e4b963"},
            {"key": "scheduled", "name": "Scheduled", "category": "in_progress", "wip_limit": None, "color": "#6b3a8e"},
            {"key": "live", "name": "Live", "category": "done", "wip_limit": None, "color": "#67a671"},
        ],
        "settings": {"estimation": "hours", "points_scale": [1, 2, 3, 5, 8], "sprint_length_days": 7, "working_days": [0, 1, 2, 3, 4], "default_type": "deliverable", "board_group_by": "none"},
        "labels": ["social", "email", "web", "events", "pr"],
    },
    "hardware-product": {
        "name": "Hardware product",
        "tagline": "Milestones, builds, tests. Physical things take real time.",
        "icon": "🔩",
        "methodology": "hybrid",
        "item_types": [
            {"key": "milestone", "name": "Milestone", "plural": "Milestones", "icon": "🏔️", "color": "#6b3a8e", "level": 0},
            {"key": "subsystem", "name": "Subsystem", "plural": "Subsystems", "icon": "⚙️", "color": "#306376", "level": 1},
            {"key": "work_package", "name": "Work package", "plural": "Work packages", "icon": "📦", "color": "#27cfc3", "level": 2},
            {"key": "test", "name": "Test", "plural": "Tests", "icon": "🧪", "color": "#e4b963", "level": 2},
            {"key": "issue", "name": "Issue", "plural": "Issues", "icon": "⚠️", "color": "#bc553c", "level": 2},
        ],
        "workflow": [
            {"key": "backlog", "name": "Backlog", "category": "todo", "wip_limit": None, "color": "#676767"},
            {"key": "design", "name": "Design", "category": "in_progress", "wip_limit": None, "color": "#27cfc3"},
            {"key": "build", "name": "Build", "category": "in_progress", "wip_limit": None, "color": "#e4b963"},
            {"key": "test", "name": "Test", "category": "in_progress", "wip_limit": None, "color": "#6b3a8e"},
            {"key": "accepted", "name": "Accepted", "category": "done", "wip_limit": None, "color": "#67a671"},
        ],
        "settings": {"estimation": "hours", "points_scale": [1, 2, 3, 5, 8, 13], "sprint_length_days": 21, "working_days": [0, 1, 2, 3, 4], "default_type": "work_package", "board_group_by": "none"},
        "labels": ["mechanical", "electrical", "firmware", "supply-chain"],
    },
    "operations": {
        "name": "Operations / IT",
        "tagline": "Requests, changes, incidents. Keep the lights on.",
        "icon": "🛠️",
        "methodology": "kanban",
        "item_types": [
            {"key": "initiative", "name": "Initiative", "plural": "Initiatives", "icon": "🗺️", "color": "#6b3a8e", "level": 0},
            {"key": "request", "name": "Request", "plural": "Requests", "icon": "📨", "color": "#27cfc3", "level": 1},
            {"key": "change", "name": "Change", "plural": "Changes", "icon": "🔁", "color": "#e4b963", "level": 1},
            {"key": "incident", "name": "Incident", "plural": "Incidents", "icon": "🚨", "color": "#bc553c", "level": 1},
        ],
        "workflow": [
            {"key": "new", "name": "New", "category": "todo", "wip_limit": None, "color": "#676767"},
            {"key": "triaged", "name": "Triaged", "category": "todo", "wip_limit": 10, "color": "#c5c2c2"},
            {"key": "in_progress", "name": "In Progress", "category": "in_progress", "wip_limit": 5, "color": "#27cfc3"},
            {"key": "waiting", "name": "Waiting", "category": "in_progress", "wip_limit": None, "color": "#e4b963"},
            {"key": "resolved", "name": "Resolved", "category": "done", "wip_limit": None, "color": "#67a671"},
        ],
        "settings": {"estimation": "throughput", "points_scale": [1, 2, 3, 5], "sprint_length_days": 7, "working_days": [0, 1, 2, 3, 4], "default_type": "request", "board_group_by": "none"},
        "labels": ["network", "accounts", "hardware", "security"],
    },
    "custom": {
        "name": "Blank / custom",
        "tagline": "Start from a minimal setup and shape it yourself.",
        "icon": "✨",
        "methodology": "hybrid",
        "item_types": [
            {"key": "goal", "name": "Goal", "plural": "Goals", "icon": "🎯", "color": "#6b3a8e", "level": 0},
            {"key": "item", "name": "Item", "plural": "Items", "icon": "📝", "color": "#27cfc3", "level": 1},
        ],
        "workflow": [
            {"key": "todo", "name": "To do", "category": "todo", "wip_limit": None, "color": "#676767"},
            {"key": "doing", "name": "Doing", "category": "in_progress", "wip_limit": None, "color": "#27cfc3"},
            {"key": "done", "name": "Done", "category": "done", "wip_limit": None, "color": "#67a671"},
        ],
        "settings": {"estimation": "points", "points_scale": [1, 2, 3, 5, 8], "sprint_length_days": 14, "working_days": [0, 1, 2, 3, 4], "default_type": "item", "board_group_by": "none"},
        "labels": [],
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [
        {"key": k, "name": v["name"], "tagline": v["tagline"], "icon": v["icon"], "methodology": v["methodology"],
         "item_types": v["item_types"], "workflow": v["workflow"], "settings": v["settings"]}
        for k, v in TEMPLATES.items()
    ]


def get_template(key: str) -> dict[str, Any]:
    return deepcopy(TEMPLATES.get(key) or TEMPLATES["custom"])


def default_evm(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "enabled": False,
        "currency": "USD",
        "bac": 0.0,  # budget at completion
        "cost_per_point": 0.0,  # used when actual cost isn't tracked explicitly
        "cost_per_hour": 0.0,
        "planned_points": 0.0,  # total scope in points at baseline
        "planned_sprints": 0,
        "start_date": None,
        "end_date": None,
        "baseline_locked_at": None,
        "method": "points",  # points | hours | count : what counts as earned value
    }


def status_category(project_workflow: list[dict], status_key: str) -> str:
    for s in project_workflow:
        if s["key"] == status_key:
            return s["category"]
    return "todo"


def first_status(project_workflow: list[dict], category: str = "todo") -> str:
    for s in project_workflow:
        if s["category"] == category:
            return s["key"]
    return project_workflow[0]["key"] if project_workflow else "backlog"
