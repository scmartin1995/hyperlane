"""Demo project: "Atlas Customer Portal" — 5 people, ~45 items, 3 closed sprints with real-looking history, 1 active.

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
    {"name": "Nova Reyes", "role": "lead", "emoji": "🧭", "color": "#e4b963",
     "skills": ["architecture", "python", "react"], "email": "nova@atlas.example",
     "bio": "Engineering lead. Keeps scope honest and sprints realistic."},
    {"name": "Kai Tanaka", "role": "developer", "emoji": "💻", "color": "#27cfc3",
     "skills": ["react", "typescript", "accessibility"], "email": "kai@atlas.example",
     "bio": "Front-end engineer. Owns the portal UI and the design system."},
    {"name": "Priya Okafor", "role": "developer", "emoji": "🛠️", "color": "#bc553c",
     "skills": ["python", "fastapi", "sqlalchemy", "infra"], "email": "priya@atlas.example",
     "bio": "Backend engineer. APIs, billing integrations and the occasional 3am hotfix."},
    {"name": "Marco Lindqvist", "role": "qa", "emoji": "🧪", "color": "#67a671",
     "skills": ["playwright", "testing", "automation"], "email": "marco@atlas.example",
     "bio": "Finds the bug before customers do. Usually."},
    {"name": "Zara Chen", "role": "po", "emoji": "🎨", "color": "#6b3a8e",
     "skills": ["product", "ux", "figma"], "email": "zara@atlas.example",
     "bio": "Product owner. Decides what ships and speaks for the customer.", "hours_per_week": 32},
]  # fmt: skip

# leaf: (type, title, points, assignee idx, sprint no (0 = backlog), outcome, description, acceptance criteria)
# outcomes: closed sprints -> "done" | "carry" (finished early next sprint); active -> done/review/in_progress/ready;
# backlog -> "backlog" | "ready"
EPICS: list[dict[str, Any]] = [
    {
        "title": "Account & identity",
        "description": "Getting in and managing who has access. Every other feature depends on it.",
        "features": [
            {
                "title": "Sign-in & SSO",
                "description": "Magic-link, password and SAML sign-in.",
                "items": [
                    ("story", "Magic-link sign-in", 5, 1, 1, "done",
                     "Let customers sign in with a one-time email link instead of a password.",
                     "- Link expires after 15 minutes\n- Works from mobile mail apps\n- Rate limited per address"),
                    ("story", "SAML single sign-on", 8, 1, 1, "done",
                     "Enterprise customers sign in through their own identity provider.",
                     "- Okta and Azure AD verified\n- Just-in-time user provisioning\n- Org admins can enforce SSO"),
                    ("story", "Session timeout and re-authentication", 5, 2, 1, "carry",
                     "Idle sessions expire; sensitive pages ask the user to confirm their identity again.",
                     "- Idle timeout configurable per org\n- Re-auth before changing billing details\n- No form data lost on timeout"),
                    ("bug", "Login loop after password reset", 3, 2, 1, "done",
                     "After resetting a password, Safari users are redirected back to the login page.",
                     "- Session cookie set before redirect\n- Repro passes on Safari 18"),
                    ("task", "Rotate signing keys for auth tokens", 2, 0, 1, "done",
                     "Move token signing keys to scheduled rotation.",
                     "- Rotation every 90 days\n- Old keys valid for one overlap window"),
                ],
            },
            {
                "title": "User management",
                "description": "Invite teammates, assign roles, remove access.",
                "items": [
                    ("story", "Invite teammates by email", 8, 1, 1, "done",
                     "Org admins invite people by email and choose their role up front.",
                     "- Bulk invite up to 50 addresses\n- Pending invites can be revoked\n- Invite email uses the org's logo"),
                    ("story", "Role-based permissions", 3, 2, 1, "done",
                     "Admin, member and billing-only roles with clear boundaries.",
                     "- Billing-only users can't see tickets\n- Role changes apply immediately"),
                    ("story", "Audit log of user changes", 3, 2, 2, "done",
                     "Every invite, role change and removal is recorded.",
                     "- Who, what and when for each change\n- Exportable to CSV"),
                    ("bug", "Removed users keep API access", 2, 3, 2, "done",
                     "Personal API tokens survive when an admin removes the user.",
                     "- Tokens revoked on removal\n- Regression test covers token revocation"),
                ],
            },
        ],
    },
    {
        "title": "Billing & invoices",
        "description": "Customers see what they owe and pay it without emailing finance.",
        "features": [
            {
                "title": "Invoices",
                "description": "Browse, filter and download invoices.",
                "items": [
                    ("story", "Invoice list with filters", 5, 2, 2, "done",
                     "A paginated invoice list filterable by status, date range and amount.",
                     "- Filters combine\n- Loads in under 300ms for 5,000 invoices\n- Status shown as paid / due / overdue"),
                    ("story", "Usage-based invoice line items", 8, 2, 2, "carry",
                     "Break metered charges down by product and day so customers can reconcile their bill.",
                     "- Line items grouped by product\n- Daily usage chart per line\n- Totals match the ERP to the cent"),
                    ("spike", "Evaluate invoice PDF libraries", 3, 0, 2, "done",
                     "Compare three PDF generators on fidelity, speed and licensing.",
                     "- Written recommendation with numbers\n- Prototype branch for the chosen library"),
                    ("task", "Sync invoices from the ERP nightly", 5, 2, 2, "done",
                     "A scheduled job pulls new and updated invoices from the ERP.",
                     "- Idempotent on re-run\n- Failures alert the on-call channel"),
                ],
            },
            {
                "title": "Payments",
                "description": "Pay by card or bank transfer.",
                "items": [
                    ("story", "Pay an invoice by card", 3, 1, 3, "done",
                     "Pay a single invoice by card with 3-D Secure.",
                     "- Receipt emailed on success\n- Failed payments show a clear reason"),
                    ("story", "Saved payment methods", 2, 2, 3, "done",
                     "Customers save a card or bank account for future payments.",
                     "- Default method selectable\n- Removing a method needs confirmation"),
                    ("bug", "Currency shows USD for EU customers", 1, 3, 3, "done",
                     "Invoice totals render with a dollar sign for accounts billed in euros.",
                     "- Currency taken from the account\n- Unit test covers EUR and GBP"),
                    ("story", "Autopay for recurring invoices", 3, 1, 3, "carry",
                     "Charge the saved payment method automatically when an invoice is issued.",
                     "- Opt-in per account\n- Email 3 days before charging"),
                ],
            },
        ],
    },
    {
        "title": "Support center",
        "description": "Self-service help and support tickets in one place.",
        "features": [
            {
                "title": "Tickets",
                "description": "Open, track and reply to support tickets.",
                "items": [
                    ("story", "Ticket list and detail view", 8, 1, 2, "done",
                     "Customers see all their tickets, with status, the full thread and who's handling it.",
                     "- Sort by last update\n- Thread shows staff and customer replies\n- Unread replies highlighted"),
                    ("story", "File attachments on tickets", 5, 2, 3, "done",
                     "Attach screenshots and logs to a ticket; files are virus-scanned before staff see them.",
                     "- Up to 10MB per file\n- Scan result visible to staff\n- Blocked files notify the uploader"),
                    ("bug", "Ticket replies lose formatting", 2, 1, 3, "done",
                     "Bulleted lists in replies arrive as one long paragraph.",
                     "- Markdown preserved end to end\n- Verified in Chrome and Firefox"),
                ],
            },
            {
                "title": "Knowledge base",
                "description": "Searchable help articles that deflect tickets.",
                "items": [
                    ("story", "Help article search", 5, 1, 3, "done",
                     "Full-text search across help articles with highlighted matches.",
                     "- Typo tolerant\n- Results in under 200ms"),
                    ("story", "Article feedback", 5, 4, 3, "done",
                     "Readers mark an article as helpful or not, with an optional comment.",
                     "- One vote per user per article\n- Weekly report of the least helpful articles"),
                    ("story", "Suggested articles while writing a ticket", 3, 1, 4, "done",
                     "As a customer types a ticket subject, relevant articles appear underneath.",
                     "- Top 3 suggestions\n- Track how often a suggestion prevents a ticket"),
                    ("task", "Help center icon set", 2, 4, 4, "review",
                     "24 icons for article categories.",
                     "- SVG on a 24px grid\n- Light and dark variants"),
                ],
            },
        ],
    },
    {
        "title": "Launch readiness",
        "description": "What has to be true before general availability: observability, onboarding, accessibility.",
        "features": [
            {
                "title": "Observability",
                "description": "Know what's happening in production before customers tell us.",
                "items": [
                    ("story", "Error reporting pipeline", 3, 2, 4, "done",
                     "Front-end and API errors are captured with context and grouped by cause.",
                     "- Errors grouped by signature\n- Personal data scrubbed from reports"),
                    ("story", "Performance dashboard", 5, 2, 4, "in_progress",
                     "Page load, API latency and error rate on one dashboard.",
                     "- p50/p95 for each metric\n- Alert thresholds visible"),
                    ("task", "Alerting rules for the API", 2, 2, 4, "ready",
                     "Page on p95 latency over 800ms for 5 minutes or an error rate over 2%.",
                     "- Rules in code\n- Test alert fired and acknowledged"),
                ],
            },
            {
                "title": "Onboarding",
                "description": "First five minutes: from invite to a first useful action.",
                "items": [
                    ("story", "Guided setup checklist", 5, 1, 4, "in_progress",
                     "A checklist on the home page that walks new admins through setup.",
                     "- Five steps with progress\n- Dismissible once complete\n- Each step deep-links to the right page"),
                    ("story", "Contextual tooltips on first visit", 2, 1, 4, "ready",
                     "Short tooltips explain key controls the first time someone sees them.",
                     "- Shown once per user\n- Dismissed per tooltip"),
                    ("story", "Company profile setup", 3, 4, 0, "ready",
                     "Admins add the company name, logo and billing contact during setup.",
                     "- Logo upload with crop\n- Can be changed later in settings"),
                    ("bug", "Setup checklist skips step 3 on mobile", 1, 3, 0, "backlog",
                     "On narrow screens the 'invite your team' step never marks as complete.",
                     "- Step 3 completes on mobile\n- Playwright test at 375px width"),
                    ("story", "Dark mode", 5, 1, 0, "ready",
                     "A dark theme that follows the system setting, with a manual override.",
                     "- All pages pass contrast checks\n- Preference saved per user"),
                    ("story", "Export data to CSV", 3, 2, 0, "ready",
                     "Admins export users, invoices and tickets to CSV.",
                     "- Opens cleanly in Excel\n- Large exports emailed when ready"),
                    ("story", "Usage analytics for admins", 8, 0, 0, "backlog",
                     "A page showing seat usage, active users and ticket volume over time.",
                     "- 30/90/365-day ranges\n- Downloadable as CSV"),
                    ("story", "French and German translations", 5, 1, 0, "backlog",
                     "Translate the portal UI and system emails into French and German.",
                     "- Language picker in profile\n- No untranslated strings on core pages"),
                    ("story", "In-app announcements", 3, 3, 0, "ready",
                     "Admins of the portal post short announcements shown on the home page.",
                     "- Scheduled start and end dates\n- Dismissible per user"),
                    ("task", "Webhook delivery logs", 2, 2, 0, "backlog",
                     "Show recent webhook deliveries with status codes and retry history.",
                     "- Last 30 days kept\n- Manual re-send"),
                    ("story", "Notification preferences", 5, 3, 0, "ready",
                     "Users choose which emails they receive and how often.",
                     "- Per-category toggles\n- Daily digest option"),
                    ("bug", "Email digest sent twice on Mondays", 1, 0, 0, "ready",
                     "The weekly digest job runs twice after the weekend.",
                     "- One digest per user per week"),
                    ("story", "Mobile-friendly ticket view", 13, 1, 0, "backlog",
                     "Rework the ticket pages so they're usable on a phone.",
                     "- Usable at 375px width\n- Attachments viewable inline"),
                    ("story", "Custom fields on tickets", 8, 2, 0, "backlog",
                     "Org admins define extra fields that customers fill in when opening a ticket.",
                     "- Text, select and date fields\n- Required flag per field"),
                    ("spike", "Evaluate search engine options", 5, 2, 0, "backlog",
                     "Compare Postgres full-text, Meilisearch and OpenSearch for help and ticket search.",
                     "- Relevance and latency numbers\n- Go/no-go recommendation"),
                    ("task", "Cookie consent banner", 2, 4, 0, "ready",
                     "Ask once, store the choice, never load analytics without consent.",
                     "- Copy reviewed by legal\n- Choice editable in settings"),
                    ("spike", "Accessibility review", 3, 4, 0, "backlog",
                     "Audit colour contrast, keyboard navigation and screen-reader labels against WCAG 2.2 AA.",
                     "- Findings doc with severity\n- Follow-up stories created"),
                ],
            },
        ],
    },
]

COMMENTS: dict[str, list[tuple[int, str, bool]]] = {
    # item title -> [(author idx, body, is_decision)]
    "SAML single sign-on": [
        (1, "Okta flow works end to end. Azure AD rejects our signing certificate, looking into it.", False),
        (4, "Two enterprise prospects asked for this in the last week. Worth the extra days.", False),
        (0, "Decision: we support SAML only for now. OIDC waits until a customer asks for it.", True),
    ],
    "Usage-based invoice line items": [
        (2, "Grouping by product works. Daily breakdown needs a new ERP endpoint.", False),
        (0, "Decision: show daily usage for the last 90 days only, older data stays monthly.", True),
        (3, "Totals match the ERP on 40 sample accounts. One rounding difference on a EUR account.", False),
    ],
    "Ticket list and detail view": [
        (1, "List and detail are in. Inline replies are out of scope for this sprint.", False),
        (4, "Can we show who's assigned on the list? Customers ask 'is anyone looking at this?' constantly.", False),
    ],
    "Session timeout and re-authentication": [
        (2, "Timeout works, but the re-auth modal loses the form state on the billing page.", False),
        (0, "Carrying this into Sprint 2. @Priya Okafor pair with Kai on the form-state handling.", False),
    ],
    "Performance dashboard": [
        (2, "Dashboard is up for page load. API latency panel next.", False),
        (0, "Decision: the dashboard lives in Grafana, not in the portal. Customers never see it.", True),
    ],
    "Guided setup checklist": [
        (4, "Copy drafted. One line per step, the home page is already busy.", False),
        (1, "@Marco Lindqvist can you run through the checklist on a phone once it's on staging?", False),
    ],
    "Evaluate invoice PDF libraries": [
        (2, "WeasyPrint gives the best fidelity; the headless-browser option is 4x slower.", False),
        (0, "Decision: WeasyPrint. Prototype branch is `billing/pdf-weasyprint`.", True),
    ],
    "Article feedback": [
        (4, "Early numbers: 71% helpful. The billing articles are the weakest.", False),
    ],
}

ACTION_ITEMS: list[list[dict[str, Any]]] = [
    [  # Nova
        {"title": "Write Sprint 4 goal in the sprint page", "priority": "high", "due": 1, "tags": ["sprint"]},
        {"title": "1:1 with Kai about the Safari login postmortem", "priority": "medium", "due": 3},
        {"title": "Review Priya's ERP sync PR", "priority": "high", "due": -1, "tags": ["review"]},
        {"title": "Draft GA launch checklist", "priority": "medium", "due": 9, "tags": ["launch"]},
        {"title": "Book retro room for Sprint 3", "priority": "low", "done": True},
    ],
    [  # Kai
        {"title": "Profile setup checklist render time on low-end laptops", "priority": "high", "due": 2, "tags": ["perf"]},
        {"title": "Reply to the attachment preview thread", "priority": "low", "due": 0},
        {"title": "Show assignee on the ticket list", "priority": "medium", "tags": ["support"]},
        {"title": "Update the SSO troubleshooting notes in the wiki", "priority": "low", "done": True},
    ],
    [  # Priya
        {"title": "Rotate the ERP API credentials", "priority": "critical", "due": -2, "tags": ["infra", "security"]},
        {"title": "Finish the API latency panel on the dashboard", "priority": "high", "due": 2},
        {"title": "Write runbook for ERP sync failures", "priority": "medium", "due": 6, "tags": ["ops"]},
        {"title": "Benchmark invoice list query with 50k rows", "priority": "low"},
    ],
    [  # Marco
        {"title": "Mobile viewport fixtures for Playwright", "priority": "high", "due": 4, "tags": ["testing"]},
        {"title": "Re-run the currency regression on all locales", "priority": "medium", "due": 1},
        {"title": "File the flaky invite-email test with a repro", "priority": "medium", "done": True},
        {"title": "Run through the setup checklist on a phone", "priority": "medium", "due": 2},
    ],
    [  # Zara
        {"title": "Customer interview: company profile setup", "priority": "high", "due": 3, "tags": ["research"]},
        {"title": "Prioritise accessibility spike for Sprint 5", "priority": "medium", "due": 8},
        {"title": "Update the GA roadmap slide", "priority": "low", "due": -3},
        {"title": "Decide on autopay default (opt-in vs opt-out)", "priority": "high", "tags": ["decision"]},
        {"title": "Send article feedback report to support", "priority": "low", "done": True},
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
                "name": self.project_name, "key": "AP", "template": "software-scrum",
                "description": "Self-service portal for Atlas customers: accounts, billing and support in one place. "
                "General availability is the goal for this quarter.",
                "icon": "🧭", "color": "#6b3a8e", "lead_id": lead.id,
                "settings": {"start_date": s1_start.isoformat(),
                             "target_end_date": (s1_start + timedelta(days=8 * 14 - 1)).isoformat()},
                "labels": ["auth", "billing", "support", "ui", "infra", "tech-debt", "ga-blocker"],
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
                    1: "Customers can sign in and invite their team.",
                    2: "Billing basics: see invoices, track support tickets.",
                    3: "Pay online and find answers without opening a ticket.",
                    4: "GA readiness: observe production, onboard new customers.",
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
        label_for = {"Account & identity": "auth", "Billing & invoices": "billing", "Support center": "support",
                     "Launch readiness": "ga-blocker"}  # fmt: skip
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
            self._activity("work_item", item.id, "moved", f"{self.project.key}-{item.number} moved from {status} to {st}", assignee, at,
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
            self._activity("work_item", parent.id, "moved", f"{self.project.key}-{parent.number} moved from backlog to in_progress",
                           lead, first, {"status": ["backlog", "in_progress"]})  # fmt: skip
            parent.status, parent.started_at, parent.updated_at = "in_progress", first, first
            if all(k.status == "done" for k in kids):
                last = max(k.completed_at for k in kids if k.completed_at)
                self._transition(parent, "in_progress", "done", lead, last)
                self._activity("work_item", parent.id, "moved", f"{self.project.key}-{parent.number} moved from in_progress to done",
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
            requester_email="lena@northwind.example", subject="Download all invoices for a month",
            original_body="Hi team! Our finance team downloads every invoice one at a time each month. Could we get "
            "a way to download all invoices for a month as one zip file? It would save us an afternoon every close.",
            state="new", last_activity_at=self._dt_ago(1, 8), thread_key="<invoice-zip-1@northwind.example>",
        )  # fmt: skip
        fresh.created_at = fresh.updated_at = self._dt_ago(1, 8)
        self.db.add(fresh)
        self.db.flush()
        self.db.add(IntakeMessage(request_id=fresh.id, direction="inbound", author="lena@northwind.example",
                                  body=fresh.original_body, external_ref=fresh.thread_key))  # fmt: skip

        clar = IntakeRequest(
            project_id=self.project.id, channel="email", requester_name="Tom Becker",
            requester_email="tom@contoso.example", subject="SSO for our contractors",
            original_body="We use SSO for employees but our contractors aren't in our identity provider. Can they "
            "still get into the portal somehow? Right now we share one login, which security hates.",
            state="clarifying", questions_asked=1, max_questions=3, owner_id=self.users[4].id,
            summary="Orgs that enforce SSO need a way to let external contractors sign in without a shared login.",
            requirements={
                "problem": "Contractors aren't in the customer's identity provider, so SSO enforcement locks them out.",
                "outcome": "Contractors sign in with their own credentials while employees keep using SSO.",
                "users": "Org admins at enterprise customers; their external contractors",
                "scope_in": ["Allow-list of non-SSO users per org", "Magic-link sign-in for allow-listed users"],
                "scope_out": ["Guest accounts without an email address"],
                "acceptance": ["Allow-listed contractor signs in by magic link", "Employees still forced through SSO"],
                "constraints": ["Admins must be able to see who bypasses SSO"],
                "priority": "high", "urgency": "before their renewal next month",
                "open_questions": ["Should contractor access expire automatically?"],
                "confidence": 0.62,
                "proposed_items": [
                    {"type": "story", "title": "SSO bypass allow-list for contractors", "points": 5},
                    {"type": "story", "title": "Show SSO bypass users in the audit log", "points": 2},
                ],
            },
            last_activity_at=self._dt_ago(3, 10), thread_key="<sso-contractors-7@contoso.example>",
        )  # fmt: skip
        clar.created_at = clar.updated_at = self._dt_ago(5, 9)
        self.db.add(clar)
        self.db.flush()
        thread = [
            ("inbound", "tom@contoso.example", clar.original_body, self._dt_ago(5, 9)),
            ("outbound", "Hyperlane Agent",
             ("Thanks Tom! Two quick questions so we build the right thing: roughly how many contractors need access, "
             "and should their access stop automatically after a set date?"),
             self._dt_ago(5, 10)),
            ("inbound", "tom@contoso.example",
             ("About 15 contractors at any time. An expiry date would be great, most contracts are 3 to 6 months."),
             self._dt_ago(3, 10)),
        ]
        for direction, author, body, at in thread:
            m = IntakeMessage(request_id=clar.id, direction=direction, author=author, body=body)
            m.created_at = m.updated_at = at
            self.db.add(m)
        self.db.flush()
        from . import triage

        for req in (fresh, clar):
            self.db.refresh(req)
            triage.sync_work_item(self.db, req)

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


def seed(project_name: str = "Atlas Customer Portal", db: Session | None = None) -> dict[str, Any]:
    """Create the demo project (idempotent by project name). Pass `db` to reuse a request session."""
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
