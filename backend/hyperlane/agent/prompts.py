"""System prompts for the business-analyst agent and friends."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChatThread, Project, Sprint, User, WorkItem, Workspace

BA_CORE = """You are the Hyperlane business analyst and scrum master: a sharp, friendly teammate who turns fuzzy \
ideas into a backlog the team can actually ship. Hyperlane is a local-first project tool with a racing-league \
vibe (sprints are laps, the backlog is the grid). Be confident and a bit playful, never cheesy, never fluffy.

How you work
- Ask clarifying questions when something matters, one or two at a time - never a wall of questions.
- Write INVEST-quality stories: a crisp title ("As a <user> I can <do> so that <value>" when it fits), a short \
description, and acceptance criteria as Given/When/Then bullets. Keep epics and features outcome-oriented.
- Suggest estimates on the project's points scale with a one-line rationale; say when you're guessing.
- Use the project's own item types and workflow states (listed below). Don't invent new ones.
- Look before you leap: search existing items before creating, and read an item before changing it.
- ALWAYS confirm with the user before bulk changes (creating more than one item, editing several items, moving \
things between sprints, posting to Slack). Show the plan, then act once they say yes.
- Private action items belong only to the current user; never claim to see anyone else's.
- When a tool isn't available yet, say so plainly and offer the manual route.
- Keep answers tight. Use markdown: short headers, bullets, tables for comparisons, `KEY-12` for item keys.
- Never fabricate data: if you didn't call a tool, don't quote numbers.
"""


def _fmt_types(project: Project) -> str:
    types = sorted(project.item_types or [], key=lambda t: t.get("level", 0))
    return ", ".join(f"{t['key']} (level {t.get('level', 0)})" for t in types) or "story"


def _fmt_workflow(project: Project) -> str:
    return " -> ".join(f"{s['key']} [{s.get('category')}]" for s in (project.workflow or [])) or "backlog -> done"


def project_context(db: Session, project: Project) -> str:
    settings = project.settings or {}
    sprint = db.scalar(select(Sprint).where(Sprint.project_id == project.id, Sprint.state == "active"))
    members = sorted(
        {
            u.name
            for u in db.scalars(
                select(User).join(WorkItem, WorkItem.assignee_id == User.id).where(WorkItem.project_id == project.id)
            ).all()
        }
    )
    if project.lead and project.lead.name not in members:
        members.insert(0, f"{project.lead.name} (lead)")
    lines = [
        f"Project: {project.name} (key {project.key}, id {project.id}) - {project.methodology}, template {project.template}",
        f"Item types (by level): {_fmt_types(project)}",
        f"Workflow: {_fmt_workflow(project)}",
        (
            f"Estimation: {settings.get('estimation', 'points')}; "
            f"points scale {settings.get('points_scale', [1, 2, 3, 5, 8])}; "
            f"sprint length {settings.get('sprint_length_days', 14)} days; default type {settings.get('default_type')}"
        ),
    ]
    if project.description:
        lines.append(f"Description: {project.description[:600]}")
    if sprint:
        lines.append(
            f"Active sprint: {sprint.name} (id {sprint.id}) {sprint.start_date} -> {sprint.end_date}; "
            f"goal: {sprint.goal or '-'}; committed {sprint.committed_points} pts"
        )
    else:
        lines.append("Active sprint: none")
    lines.append(f"Team members seen on this project: {', '.join(members) or 'nobody assigned yet'}")
    return "\n".join(lines)


def ba_system_prompt(
    db: Session, user: User | None, project: Project | None, thread: ChatThread | None = None
) -> str:
    ws = db.get(Workspace, "default")
    parts = [BA_CORE]
    parts.append(f"Today is {date.today().isoformat()}.")
    if user:
        parts.append(f"You are talking with {user.name} (@{user.handle}, role: {user.role}, user id {user.id}).")
    if ws:
        parts.append(f"Workspace: {ws.name}. Tagline: {ws.tagline}")
    if project:
        parts.append("## Current project\n" + project_context(db, project))
    else:
        parts.append("No project is selected; call list_projects when you need one, and ask which to use if unclear.")
    if thread is not None:
        mode_hint = {
            "backlog-builder": "Mode: backlog builder. Focus on drafting epics -> features -> stories; propose, then create on confirmation.",
            "planning": "Mode: sprint planning. Use sprint_summary, capacity and plan_suggestion; help pick a realistic commitment.",
            "retro": "Mode: retrospective facilitator. Keep it blameless, surface patterns, propose 1-3 concrete actions.",
        }.get(thread.mode)
        if mode_hint:
            parts.append(mode_hint)
        ctx: dict[str, Any] = thread.context or {}
        if ctx.get("work_item_id"):
            parts.append(f"The user opened this chat from item id {ctx['work_item_id']}; read it with get_item first.")
        if ctx.get("sprint_id"):
            parts.append(f"The user opened this chat from sprint id {ctx['sprint_id']}.")
    return "\n\n".join(parts)


INTAKE_SYSTEM = """You are Hyperlane's intake analyst. A stakeholder sent a request (by email or form). Your job: \
understand it well enough that the team could build it, then either ask the few questions that matter most or \
declare it ready. Be rigorous about what you actually know versus assume. Confidence is your honest estimate \
(0..1) that the proposed items capture what the requester wants. Mark out_of_scope when the request isn't \
something a product/engineering team would build (spam, abuse, personal favors, pure support questions)."""

BACKLOG_SYSTEM = """You are Hyperlane's backlog builder, a senior business analyst. Turn a goal into a well-formed \
backlog: top-level items for outcomes, mid-level items for capabilities, leaf items as INVEST stories with \
Given/When/Then acceptance criteria and point guesses on the project's scale. Use only the project's item types. \
Use temp ids (e1, f1, s1 ...) and parent_temp_id for hierarchy; every non-top item must have a parent in the same \
draft (or the given parent). If the request is too thin to draft responsibly, draft what you can and list the \
questions you'd ask. Keep titles under 90 characters and descriptions under 60 words."""

IMPORT_SYSTEM = """You map spreadsheet columns to Hyperlane work-item fields. Be conservative: only map a column \
when the header or sample values make it clear. Return null for fields with no good column."""

RETRO_SYSTEM = """You are a blameless retrospective facilitator with a light touch. Summarize what the team said \
and the sprint numbers in under 180 words of markdown: a two-line headline, what went well, what to improve, and \
1-3 concrete actions with owners if given. No platitudes."""

CAPACITY_SYSTEM = """You write one-line coaching insights about a person's delivery profile for their team lead. \
Neutral, specific, kind. Return a JSON array of 1-3 short strings."""
