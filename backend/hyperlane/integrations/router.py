"""Notification router: decides which bus events become Slack / Teams messages.

`handle(event)` is subscribed to the bus and called synchronously by every emitter, so it must be
fast and must never raise: it only filters by event type and hands the work to a tiny thread pool.
`process(event)` does the actual decision + sends (synchronously; tests call it directly).

Event -> notification matrix
    work_item.updated   status / assignee / blocked changed -> project channel (threaded per item),
                        Teams card; DM to new assignee if they opted in (slack_dm + notify_assignments)
    work_item.moved     status changed -> same as above (rank-only moves are ignored)
    comment.created     source != slack -> reply in the item's Slack thread (no echo); Teams card
    sprint.started      goal + committed -> project channel + Teams
    sprint.closed       completed / carried -> project channel + Teams
    intake.*            nothing (email replies are sent by the intake flow itself)
    notification.sent   nothing (never re-notify about a notification)
`daily_digest()` is a scheduler job (09:00 local): per-project channel digest + opt-in DMs.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import ActionItem, Comment, Project, Sprint, User, WorkItem
from ..services.events import Event
from . import slack, teams
from ._common import (
    item_dict,
    item_key,
    local_today,
    pref,
    status_category,
    status_name,
    to_local_date,
    user_name,
)

log = logging.getLogger(__name__)

INTERESTING = {"work_item.updated", "work_item.moved", "comment.created", "sprint.started", "sprint.closed"}

_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hyperlane-notify")
        return _pool


def shutdown() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=False)
            _pool = None


def _any_channel_configured() -> bool:
    s = get_settings()
    return bool(s.slack_bot_token or s.teams_webhook_url)


def handle(event: Event) -> None:
    """Bus subscriber. Cheap filter, then async processing. Never raises."""
    try:
        if event.type not in INTERESTING:
            return
        if not _any_channel_configured():
            return
        _executor().submit(process, event)
    except Exception:  # pragma: no cover
        log.exception("router.handle failed")


# ---------------------------------------------------------------- targets


def _targets(project: Project | None) -> tuple[str | None, str | None]:
    """(slack channel, teams webhook) for a project, honouring per-project overrides."""
    s = get_settings()
    slack_channel = (project.slack_channel if project else None) or s.slack_default_channel
    if not s.slack_bot_token:
        slack_channel = None
    webhook = (project.teams_webhook_override if project else None) or s.teams_webhook_url
    return slack_channel, webhook


def _send_item(
    project: Project, item: WorkItem, summary: str, *, teams_title: str, teams_facts: list[tuple[str, str]]
) -> None:
    d = item_dict(item)
    slack_channel, webhook = _targets(project)
    text = f"{d['key']} {d['title']} — {summary}"
    if slack_channel:
        thread_ts = slack.item_thread_ts(item.id, slack_channel)
        if thread_ts:
            slack.post_message(
                slack_channel,
                text,
                thread_ts=thread_ts,
                kind="item_update",
                entity_type="work_item",
                entity_id=item.id,
                project_id=project.id,
            )
        else:
            slack.post_message(
                slack_channel,
                text,
                blocks=slack.format_item_blocks(d, summary),
                kind="item_update",
                entity_type="work_item",
                entity_id=item.id,
                project_id=project.id,
            )
    if webhook:
        teams.post_card(
            f"{summary}\n\n[Open {d['key']}]({d['url']})",
            title=f"{teams_title}: {d['key']} {d['title']}",
            facts=teams_facts,
            webhook=webhook,
            kind="item_update",
            entity_type="work_item",
            entity_id=item.id,
            project_id=project.id,
        )


def _change(changes: dict[str, Any], field: str) -> tuple[Any, Any] | None:
    """Accepts {field: [old, new]} or {field: {"old":..,"new":..}} or {field: new}."""
    if field not in changes:
        return None
    val = changes[field]
    if isinstance(val, (list, tuple)) and len(val) == 2:
        return val[0], val[1]
    if isinstance(val, dict) and ("new" in val or "to" in val):
        return val.get("old", val.get("from")), val.get("new", val.get("to"))
    return None, val


def _changes_of(event: Event) -> dict[str, Any]:
    data = event.data or {}
    changes = data.get("changes")
    if isinstance(changes, dict) and changes:
        return changes
    out: dict[str, Any] = {}
    if "from_status" in data or "to_status" in data:
        out["status"] = [data.get("from_status"), data.get("to_status")]
    elif "status" in data and isinstance(data["status"], (list, tuple, dict)):
        out["status"] = data["status"]
    if "assignee_id" in data and isinstance(data["assignee_id"], (list, tuple, dict)):
        out["assignee_id"] = data["assignee_id"]
    return out


# ---------------------------------------------------------------- processing


def process(event: Event) -> None:
    """Synchronous decision + send. Safe to call from tests (with slack/teams monkeypatched)."""
    try:
        if event.type in ("work_item.updated", "work_item.moved"):
            _on_item_change(event)
        elif event.type == "comment.created":
            _on_comment(event)
        elif event.type in ("sprint.started", "sprint.closed"):
            _on_sprint(event)
    except Exception:
        log.exception("notification routing failed for %s", event.type)


def _on_item_change(event: Event) -> None:
    changes = _changes_of(event)
    status_ch = _change(changes, "status")
    assignee_ch = _change(changes, "assignee_id")
    blocked_ch = _change(changes, "blocked")
    if not (status_ch or assignee_ch or blocked_ch):
        return
    with session_scope() as db:
        item = db.get(WorkItem, event.entity_id) if event.entity_id else None
        if item is None or item.is_archived:
            return
        project = item.project
        actor = user_name(db, event.actor_id) or "someone"
        parts: list[str] = []
        facts: list[tuple[str, str]] = []
        if status_ch and status_ch[0] != status_ch[1]:
            old, new = status_name(project, status_ch[0]), status_name(project, status_ch[1] or item.status)
            parts.append(f"{old} → *{new}*")
            facts.append(("Status", f"{old} → {new}"))
        if assignee_ch and assignee_ch[0] != assignee_ch[1]:
            new_name = user_name(db, assignee_ch[1]) or "Unassigned"
            parts.append(f"assigned to *{new_name}*")
            facts.append(("Assignee", new_name))
        if blocked_ch and bool(blocked_ch[0]) != bool(blocked_ch[1]):
            if blocked_ch[1]:
                reason = f" ({item.blocked_reason})" if item.blocked_reason else ""
                parts.append(f"⛔ *blocked*{reason}")
                facts.append(("Blocked", item.blocked_reason or "yes"))
            else:
                parts.append("unblocked")
                facts.append(("Blocked", "no"))
        if not parts:
            return
        facts.append(("By", actor))
        summary = ", ".join(parts) + f" by {actor}"
        _send_item(project, item, summary, teams_title="Item updated", teams_facts=facts)

        if assignee_ch and assignee_ch[1] and assignee_ch[1] != event.actor_id:
            assignee = db.get(User, assignee_ch[1])
            if (
                assignee is not None
                and assignee.slack_user_id
                and pref(assignee, "slack_dm")
                and pref(assignee, "notify_assignments")
            ):
                d = item_dict(item)
                slack.post_dm(
                    assignee.slack_user_id,
                    f"👋 {actor} assigned you <{d['url']}|{d['key']}> {d['title']}",
                    blocks=slack.format_item_blocks(d, f"Assigned to you by {actor}"),
                    kind="assignment",
                    entity_type="work_item",
                    entity_id=item.id,
                )


def _on_comment(event: Event) -> None:
    data = event.data or {}
    with session_scope() as db:
        comment = db.get(Comment, event.entity_id) if event.entity_id else None
        source = data.get("source") or (comment.source if comment else "web")
        if source == "slack":
            return  # came from a Slack thread already
        body = data.get("body") or (comment.body if comment else "")
        item_id = data.get("work_item_id") or (comment.work_item_id if comment else None)
        item = db.get(WorkItem, item_id) if item_id else None
        if item is None or not body:
            return
        project = item.project
        author = (
            (comment.author.name if comment and comment.author else None)
            or (comment.author_name if comment else None)
            or user_name(db, event.actor_id)
            or "someone"
        )
        d = item_dict(item)
        slack_channel, webhook = _targets(project)
        snippet = body if len(body) <= 1500 else body[:1500] + "…"
        if slack_channel:
            thread_ts = slack.item_thread_ts(item.id, slack_channel)
            if thread_ts:
                slack.post_message(
                    slack_channel,
                    f"💬 *{author}*: {snippet}",
                    thread_ts=thread_ts,
                    kind="comment",
                    entity_type="work_item",
                    entity_id=item.id,
                    project_id=project.id,
                )
            else:
                slack.post_message(
                    slack_channel,
                    f"💬 {author} commented on {d['key']} {d['title']}: {snippet}",
                    blocks=slack.format_item_blocks(d, f"💬 {author}: {snippet}"),
                    kind="item_update",
                    entity_type="work_item",
                    entity_id=item.id,
                    project_id=project.id,
                )
        if webhook:
            teams.post_card(
                f"{snippet}\n\n[Open {d['key']}]({d['url']})",
                title=f"{author} commented on {d['key']} {d['title']}",
                webhook=webhook,
                kind="comment",
                entity_type="work_item",
                entity_id=item.id,
                project_id=project.id,
            )


def _on_sprint(event: Event) -> None:
    with session_scope() as db:
        sprint = db.get(Sprint, event.entity_id) if event.entity_id else None
        if sprint is None:
            return
        project = sprint.project
        slack_channel, webhook = _targets(project)
        if not slack_channel and not webhook:
            return
        unit = "pts" if (project.settings or {}).get("estimation") == "points" else "items"
        data = event.data or {}
        if event.type == "sprint.started":
            committed = sprint.committed_points if unit == "pts" else sprint.committed_count
            title = f"▶️ {project.name} · {sprint.name} started"
            lines = [
                f"*{sprint.start_date} → {sprint.end_date}*",
                f"Goal: {sprint.goal or '_none set_'}",
                f"Committed: {committed:g} {unit} ({sprint.committed_count} items)",
            ]
            facts = [
                ("Dates", f"{sprint.start_date} → {sprint.end_date}"),
                ("Goal", sprint.goal or "none"),
                ("Committed", f"{committed:g} {unit}"),
            ]
            kind = "sprint_start"
        else:
            completed = sprint.completed_points if unit == "pts" else sprint.completed_count
            committed = sprint.committed_points if unit == "pts" else sprint.committed_count
            carried = data.get("carried")
            if isinstance(carried, list):
                carried_n: int | None = len(carried)
            elif isinstance(carried, int):
                carried_n = carried
            else:
                carried_n = data.get("carried_count")
            pct = f" ({completed / committed * 100:.0f}%)" if committed else ""
            title = f"🏆 {project.name} · {sprint.name} closed"
            lines = [
                f"Goal: {sprint.goal or '_none set_'}",
                f"Completed: {completed:g} / {committed:g} {unit}{pct} — {sprint.completed_count} items",
            ]
            if carried_n is not None:
                lines.append(f"Carried over: {carried_n} item(s)")
            facts = [
                ("Goal", sprint.goal or "none"),
                ("Completed", f"{completed:g} / {committed:g} {unit}{pct}"),
                ("Carried over", str(carried_n if carried_n is not None else "—")),
            ]
            kind = "sprint_close"
        text = f"*{title}*\n" + "\n".join(lines)
        if slack_channel:
            slack.post_message(
                slack_channel,
                text,
                kind=kind,
                entity_type="sprint",
                entity_id=sprint.id,
                project_id=project.id,
            )
        if webhook:
            teams.post_card(
                "\n\n".join(ln.replace("*", "**").replace("_", "") for ln in lines),
                title=title,
                facts=facts,
                webhook=webhook,
                kind=kind,
                entity_type="sprint",
                entity_id=sprint.id,
                project_id=project.id,
            )


# ---------------------------------------------------------------- daily digest


def daily_digest() -> dict[str, int]:
    """09:00 job: per-project digest to its channel; per-user private DM for opt-ins. Counts only for private data."""
    sent = {"projects": 0, "dms": 0}
    if not _any_channel_configured():
        return sent
    today = local_today()
    yesterday = today - timedelta(days=1)
    try:
        with session_scope() as db:
            projects = db.execute(select(Project).where(Project.status == "active")).scalars().all()
            for project in projects:
                slack_channel, webhook = _targets(project)
                if not slack_channel and not webhook:
                    continue
                items = (
                    db.execute(
                        select(WorkItem).where(
                            WorkItem.project_id == project.id, WorkItem.is_archived.is_(False)
                        )
                    )
                    .scalars()
                    .all()
                )
                done = [it for it in items if to_local_date(it.completed_at) == yesterday]
                wip = [it for it in items if status_category(project, it.status) == "in_progress"]
                blocked = [it for it in items if it.blocked and status_category(project, it.status) != "done"]
                if not (done or wip or blocked):
                    continue
                text = _digest_text(project, done, wip, blocked, today)
                if slack_channel:
                    slack.post_message(
                        slack_channel,
                        text,
                        kind="digest",
                        entity_type="project",
                        entity_id=project.id,
                        project_id=project.id,
                    )
                if webhook:
                    teams.post_card(
                        text.replace("*", "**"),
                        title=f"{project.icon} {project.name} — daily digest {today}",
                        facts=[
                            ("Done yesterday", str(len(done))),
                            ("In progress", str(len(wip))),
                            ("Blocked", str(len(blocked))),
                        ],
                        webhook=webhook,
                        kind="digest",
                        entity_type="project",
                        entity_id=project.id,
                        project_id=project.id,
                    )
                sent["projects"] += 1

            if get_settings().slack_bot_token:
                users = (
                    db.execute(select(User).where(User.is_active.is_(True), User.slack_user_id.is_not(None)))
                    .scalars()
                    .all()
                )
                for user in users:
                    if not pref(user, "slack_dm"):
                        continue
                    text = _user_digest_text(db, user, today)
                    if text is None:
                        continue
                    slack.post_dm(
                        user.slack_user_id, text, kind="digest", entity_type="user", entity_id=user.id
                    )
                    sent["dms"] += 1
    except Exception:
        log.exception("daily digest failed")
    return sent


def _digest_text(
    project: Project, done: list[WorkItem], wip: list[WorkItem], blocked: list[WorkItem], today
) -> str:
    def block(title: str, items: list[WorkItem], empty: str) -> str:
        if not items:
            return f"*{title}*\n  _{empty}_"
        lines = [
            f"  • {item_key(it)} {it.title}" + (f" — {it.assignee.name}" if it.assignee else "")
            for it in items[:15]
        ]
        if len(items) > 15:
            lines.append(f"  … and {len(items) - 15} more")
        return f"*{title}* ({len(items)})\n" + "\n".join(lines)

    return (
        f"*{project.icon} {project.name} — daily digest · {today.isoformat()}*\n"
        + block("✅ Done yesterday", done, "nothing finished")
        + "\n"
        + block("🔄 In progress today", wip, "nothing in progress")
        + "\n"
        + block("⛔ Blocked", blocked, "no blockers")
    )


def _user_digest_text(db, user: User, today) -> str | None:
    items = (
        db.execute(select(WorkItem).where(WorkItem.assignee_id == user.id, WorkItem.is_archived.is_(False)))
        .scalars()
        .all()
    )
    open_items = [it for it in items if status_category(it.project, it.status) != "done"]
    wip = [it for it in open_items if status_category(it.project, it.status) == "in_progress"]
    overdue = [it for it in open_items if it.due_date and it.due_date < today]
    overdue_actions = db.execute(
        select(ActionItem.id).where(
            ActionItem.owner_id == user.id,
            ActionItem.done.is_(False),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date < today,
        )
    ).all()
    n_actions = len(overdue_actions)
    if not (wip or overdue or n_actions):
        return None

    def lines(its: list[WorkItem]) -> str:
        return (
            "\n".join(f"  • <{d['url']}|{d['key']}> {d['title']}" for d in map(item_dict, its[:10]))
            or "  _none_"
        )

    text = f"*Good morning, {user.name}* · {today.isoformat()}\n*In progress* ({len(wip)})\n{lines(wip)}\n"
    text += f"*Overdue* ({len(overdue)})\n{lines(overdue)}\n"
    if n_actions:
        text += f"*Private action items overdue:* {n_actions} (open Hyperlane → Action items)"
    return text
