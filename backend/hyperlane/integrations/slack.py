"""Slack integration: Socket Mode bot (slack-bolt) + Web API posting (slack_sdk).

Nothing touches the network at import time. `start()` is only called by `integrations.start_all`
when both SLACK_BOT_TOKEN and SLACK_APP_TOKEN are set; posting helpers return None when Slack is
not configured. Every outbound message is written to `NotificationLog`.

Slash command grammar (`/hyperlane ...`), parsed by the pure `parse_command`:

    (nothing) | help                     -> help text
    mine                                 -> my open items grouped by status
    standup                              -> post yesterday/today/blockers built from my items
    todo <text>                          -> private action item for me
    ask <question>                       -> quick BA-agent answer
    <KEY-123>                            -> show the item
    <KEY-123> done|start|review|<status> -> status update
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import threading
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from ..config import get_settings
from ..db import session_scope
from ..models import ActionItem, Comment, NotificationLog, Project, User, WorkItem
from ..services.events import bus
from ._common import (
    item_dict,
    item_key,
    item_url,
    local_today,
    record_notification,
    status_category,
    status_name,
    to_local_date,
)

log = logging.getLogger(__name__)

KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{0,9})-(\d+)$")
MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")

HELP_TEXT = (
    "*Hyperlane commands*\n"
    "• `/hyperlane mine` — your open items, grouped by status\n"
    "• `/hyperlane HL-12 done|start|review|<status>` — move an item\n"
    "• `/hyperlane HL-12` — show an item\n"
    "• `/hyperlane todo <text>` — add a private action item (only you can see it)\n"
    "• `/hyperlane ask <question>` — ask the Hyperlane BA agent\n"
    "• `/hyperlane standup` — post your yesterday / today / blockers\n"
    "• `/hyperlane help` — this message"
)
UNLINKED_TEXT = (
    "I don't know who you are yet. Link your profile in Hyperlane → People "
    "(set your Slack user id, or make your Hyperlane email match your Slack email)."
)

_STATUS_ALIASES: dict[str, str] = {
    "start": "in_progress",
    "started": "in_progress",
    "doing": "in_progress",
    "wip": "in_progress",
    "progress": "in_progress",
    "done": "done",
    "close": "done",
    "closed": "done",
    "complete": "done",
    "completed": "done",
    "finish": "done",
    "finished": "done",
    "todo": "todo",
    "backlog": "todo",
    "reopen": "todo",
}

# runtime state (only populated by start())
_bolt_app: Any = None
_handler: Any = None
_thread: threading.Thread | None = None
_client: Any = None
_connected = False
_last_error: str | None = None


# ---------------------------------------------------------------- pure helpers


def parse_command(text: str | None) -> dict[str, Any]:
    """Turn the slash-command text into a structured command. Pure, no I/O."""
    raw = (text or "").strip()
    if not raw:
        return {"cmd": "help"}
    parts = raw.split(None, 1)
    head = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    low = head.lower()
    if low in ("help", "?"):
        return {"cmd": "help"}
    if low in ("mine", "me", "my"):
        return {"cmd": "mine"}
    if low == "standup":
        return {"cmd": "standup"}
    if low == "todo":
        if not rest:
            return {"cmd": "error", "text": "Usage: `/hyperlane todo <text>`"}
        return {"cmd": "todo", "text": rest}
    if low == "ask":
        if not rest:
            return {"cmd": "error", "text": "Usage: `/hyperlane ask <question>`"}
        return {"cmd": "ask", "text": rest}
    m = KEY_RE.match(head)
    if m:
        key = f"{m.group(1).upper()}-{int(m.group(2))}"
        if not rest:
            return {"cmd": "show", "key": key}
        status = rest.split()[0].lower()
        return {"cmd": "status", "key": key, "status": status, "text": rest}
    return {"cmd": "unknown", "text": raw}


def resolve_status(project: Project, word: str) -> str | None:
    """Map a user-typed status word (`done`, `start`, `review`, a key or a name) to a workflow key."""
    word = (word or "").strip().lower()
    workflow = list(project.workflow or [])
    if not workflow or not word:
        return None
    keys = {st["key"]: st for st in workflow}
    if word in keys:
        return word
    alias = _STATUS_ALIASES.get(word)
    if alias == "in_progress":
        for st in workflow:
            if st.get("category") == "in_progress":
                return st["key"]
    elif alias == "done":
        for st in reversed(workflow):
            if st.get("category") == "done":
                return st["key"]
    elif alias == "todo":
        for st in workflow:
            if st.get("category") == "todo":
                return st["key"]
    for st in workflow:
        if st.get("name", "").lower() == word:
            return st["key"]
    for st in workflow:
        if st["key"].startswith(word) or st.get("name", "").lower().startswith(word):
            return st["key"]
    for st in workflow:
        if word in st["key"] or word in st.get("name", "").lower():
            return st["key"]
    return None


def format_item_blocks(item: dict[str, Any], change_summary: str | None = None) -> list[dict[str, Any]]:
    """Block Kit for an item message: header line, status/assignee fields, link, change summary."""
    key = item.get("key") or "?"
    title = item.get("title") or ""
    url = item.get("url") or item_url(item.get("id", ""))
    status_txt = item.get("status_name") or item.get("status") or "—"
    badge = {"done": "✅", "in_progress": "🔄", "todo": "📋"}.get(item.get("category") or "", "📋")
    if item.get("blocked"):
        badge = "⛔"
    assignee = item.get("assignee_name") or "Unassigned"
    fields = [
        {"type": "mrkdwn", "text": f"*Status*\n{badge} {status_txt}"},
        {"type": "mrkdwn", "text": f"*Assignee*\n{assignee}"},
    ]
    if item.get("priority"):
        fields.append({"type": "mrkdwn", "text": f"*Priority*\n{item['priority']}"})
    if item.get("points") is not None:
        fields.append({"type": "mrkdwn", "text": f"*Points*\n{item['points']:g}"})
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*<{url}|{key}>* {_esc(title)}"}},
        {"type": "section", "fields": fields[:10]},
    ]
    if change_summary:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _esc(change_summary)}]})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open in Hyperlane"},
                    "url": url,
                    "action_id": "open_item",
                }
            ],
        }
    )
    return blocks


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _item_line(d: dict[str, Any]) -> str:
    return f"• <{d['url']}|{d['key']}> {_esc(d['title'])}"


# ---------------------------------------------------------------- web api client


def client() -> Any:
    """A `slack_sdk.WebClient` or None when SLACK_BOT_TOKEN is not set."""
    global _client
    s = get_settings()
    if not s.slack_bot_token:
        return None
    if _client is None:
        try:
            from slack_sdk import WebClient

            _client = WebClient(token=s.slack_bot_token)
        except ImportError:  # pragma: no cover
            log.warning("slack_sdk not installed")
            return None
    return _client


def post_message(
    channel: str | None,
    text: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
    thread_ts: str | None = None,
    kind: str = "message",
    entity_type: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
) -> str | None:
    """Post to a channel (id or #name). Returns the message `ts`, or None. Always logs."""
    channel = channel or get_settings().slack_default_channel
    if not channel:
        log.warning("slack: no channel to post to (set SLACK_DEFAULT_CHANNEL or project.slack_channel)")
        return None
    cli = client()
    if cli is None:
        log.warning("slack: not configured; dropping message to %s", channel)
        return None
    ts: str | None = None
    err: str | None = None
    try:
        resp = cli.chat_postMessage(
            channel=channel, text=text, blocks=blocks, thread_ts=thread_ts, unfurl_links=False
        )
        ts = resp.get("ts")
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        err = str(e)
        log.error("slack post failed (%s): %s", channel, err)
    record_notification(
        channel="slack",
        target=channel,
        kind=kind,
        body=text,
        ok=ts is not None,
        error=err,
        external_ref=ts,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        meta={"thread_ts": thread_ts} if thread_ts else {},
    )
    return ts


def post_dm(
    slack_user_id: str,
    text: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
    kind: str = "dm",
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> str | None:
    """Open (or reuse) the IM with a user and post there. Returns ts or None. Always logs."""
    cli = client()
    if cli is None:
        log.warning("slack: not configured; dropping DM to %s", slack_user_id)
        return None
    ts: str | None = None
    err: str | None = None
    try:
        opened = cli.conversations_open(users=[slack_user_id])
        channel_id = opened["channel"]["id"]
        resp = cli.chat_postMessage(channel=channel_id, text=text, blocks=blocks, unfurl_links=False)
        ts = resp.get("ts")
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        err = str(e)
        log.error("slack DM failed (%s): %s", slack_user_id, err)
    record_notification(
        channel="slack",
        target=slack_user_id,
        kind=kind,
        body=text,
        ok=ts is not None,
        error=err,
        external_ref=ts,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return ts


def item_thread_ts(entity_id: str, channel: str | None = None) -> str | None:
    """The `ts` of the first successful item message for this item (so updates thread under it)."""
    with session_scope() as db:
        q = (
            select(NotificationLog.external_ref)
            .where(
                NotificationLog.channel == "slack",
                NotificationLog.kind == "item_update",
                NotificationLog.entity_id == entity_id,
                NotificationLog.ok.is_(True),
                NotificationLog.external_ref.is_not(None),
            )
            .order_by(NotificationLog.created_at.asc())
        )
        if channel:
            q = q.where(NotificationLog.target == channel)
        return db.execute(q.limit(1)).scalar_one_or_none()


def item_for_thread_ts(db, thread_ts: str) -> WorkItem | None:
    """Reverse lookup: which work item does a Slack message belong to (root message only)."""
    row = db.execute(
        select(NotificationLog)
        .where(
            NotificationLog.channel == "slack",
            NotificationLog.external_ref == thread_ts,
            NotificationLog.entity_type == "work_item",
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None or not row.entity_id:
        return None
    return db.get(WorkItem, row.entity_id)


def test_connection() -> dict[str, Any]:
    s = get_settings()
    if not s.slack_bot_token:
        return {"ok": False, "detail": "SLACK_BOT_TOKEN not set"}
    cli = client()
    if cli is None:
        return {"ok": False, "detail": "slack_sdk not available"}
    try:
        resp = cli.auth_test()
        who = f"{resp.get('user')} in {resp.get('team')}"
        detail = f"auth.test ok as {who}"
        if not s.slack_app_token:
            detail += " (SLACK_APP_TOKEN missing: Socket Mode inbound disabled)"
        return {"ok": True, "detail": detail}
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        return {"ok": False, "detail": f"auth.test failed: {e}"}


# ---------------------------------------------------------------- users


def resolve_user(db, slack_user_id: str | None, *, lookup_email: bool = True) -> User | None:
    """Slack user id -> Hyperlane `User`. Falls back to users.info email match and persists the id."""
    if not slack_user_id:
        return None
    user = db.execute(select(User).where(User.slack_user_id == slack_user_id).limit(1)).scalar_one_or_none()
    if user is not None:
        return user
    if not lookup_email:
        return None
    cli = client()
    if cli is None:
        return None
    try:
        info = cli.users_info(user=slack_user_id)
        email = (info.get("user", {}).get("profile", {}) or {}).get("email")
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        log.warning("users.info failed for %s: %s", slack_user_id, e)
        return None
    if not email:
        return None
    user = db.execute(
        select(User).where(func.lower(User.email) == email.lower(), User.is_active.is_(True)).limit(1)
    ).scalar_one_or_none()
    if user is not None:
        user.slack_user_id = slack_user_id
        db.commit()
        bus.emit("user.updated", entity_type="user", entity_id=user.id, data={"slack_user_id": slack_user_id})
    return user


def slack_display_name(slack_user_id: str | None) -> str | None:
    cli = client()
    if cli is None or not slack_user_id:
        return None
    try:
        info = cli.users_info(user=slack_user_id).get("user", {})
        prof = info.get("profile", {}) or {}
        return prof.get("display_name") or prof.get("real_name") or info.get("real_name") or info.get("name")
    except Exception:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        return None


# ---------------------------------------------------------------- command execution (no Slack network)


def find_item_by_key(db, key: str) -> WorkItem | None:
    m = KEY_RE.match(key or "")
    if not m:
        return None
    pkey, num = m.group(1).upper(), int(m.group(2))
    project = db.execute(select(Project).where(func.upper(Project.key) == pkey).limit(1)).scalar_one_or_none()
    if project is None:
        return None
    return db.execute(
        select(WorkItem).where(WorkItem.project_id == project.id, WorkItem.number == num).limit(1)
    ).scalar_one_or_none()


def my_open_items(db, user: User) -> list[WorkItem]:
    items = (
        db.execute(
            select(WorkItem)
            .where(WorkItem.assignee_id == user.id, WorkItem.is_archived.is_(False))
            .order_by(WorkItem.rank.asc())
        )
        .scalars()
        .all()
    )
    return [it for it in items if status_category(it.project, it.status) != "done"]


def _agent_quick(prompt: str, system: str | None = None) -> str | None:
    try:
        from ..agent import quick
    except ImportError:
        return None
    try:
        res = quick(prompt, system=system) if system else quick(prompt)
        if inspect.isawaitable(res):
            res = asyncio.run(res)
        return str(res) if res else None
    except Exception as e:  # noqa: BLE001 - the agent's failure must not break the command
        log.error("agent.quick failed: %s", e)
        return f"The agent could not answer right now ({e.__class__.__name__})."


def _apply_status(db, item: WorkItem, new_status: str, actor: User) -> str | None:
    """Status change via backend-core's update_item; returns an error string or None."""
    try:
        from ..services.items import update_item
    except ImportError:
        return "Item updates are not available yet (core item service missing)."
    try:
        update_item(db, item, {"status": new_status}, actor)
        db.commit()
    except ValueError as e:
        db.rollback()
        return str(e)
    except Exception as e:
        db.rollback()
        log.exception("update_item failed")
        return f"Update failed: {e.__class__.__name__}"
    return None


def _create_todo(db, user: User, text: str) -> ActionItem | None:
    data = {"title": text[:300], "source": "slack"}
    try:
        from ..services.action_items import create_action_item

        res = create_action_item(db, user, data)
        db.commit()
        return res
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001 - reported to the user as a failure
        db.rollback()
        log.error("create_action_item failed: %s", e)
        return None
    ai = ActionItem(owner_id=user.id, title=data["title"], source="slack")
    db.add(ai)
    db.commit()
    bus.emit("action_item.created", entity_type="action_item", entity_id=ai.id, actor_id=user.id)
    return ai


def add_slack_comment(
    db, item: WorkItem, body: str, *, author: User | None, author_name: str | None, external_ref: str | None
) -> Comment | None:
    try:
        from ..services.items import add_comment

        c = add_comment(
            db, item, body, author=author, author_name=author_name, source="slack", external_ref=external_ref
        )
        db.commit()
        return c
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001 - reported to the user as a failure
        db.rollback()
        log.error("add_comment failed: %s", e)
        return None
    c = Comment(
        work_item_id=item.id,
        author_id=author.id if author else None,
        author_name=author_name if author is None else None,
        body=body,
        source="slack",
        external_ref=external_ref,
    )
    db.add(c)
    db.commit()
    bus.emit(
        "comment.created",
        project_id=item.project_id,
        entity_type="comment",
        entity_id=c.id,
        actor_id=author.id if author else None,
        data={"work_item_id": item.id, "source": "slack", "body": body},
    )
    return c


def handle_command(db, user: User | None, parsed: dict[str, Any]) -> dict[str, Any]:
    """Execute a parsed slash command. Returns {text, response_type, blocks?}. No Slack network."""
    cmd = parsed.get("cmd")
    if cmd == "help":
        return _eph(HELP_TEXT)
    if cmd == "error":
        return _eph(parsed.get("text") or HELP_TEXT)
    if cmd == "unknown":
        return _eph(f"Didn't understand `{parsed.get('text', '')}`.\n{HELP_TEXT}")
    if user is None:
        return _eph(UNLINKED_TEXT)

    if cmd == "mine":
        items = my_open_items(db, user)
        if not items:
            return _eph("Nothing assigned to you right now. Clean track ahead.")
        groups: dict[str, list[str]] = {}
        for it in items:
            d = item_dict(it)
            label = f"{d['status_name']} ({d['project_key']})"
            groups.setdefault(label, []).append(_item_line(d))
        out = [f"*Your open items* ({len(items)})"]
        for label, lines in groups.items():
            out.append(f"\n*{label}*\n" + "\n".join(lines))
        return _eph("\n".join(out))

    if cmd == "show":
        item = find_item_by_key(db, parsed["key"])
        if item is None:
            return _eph(f"No item `{parsed['key']}` found.")
        d = item_dict(item)
        return _eph(f"{d['key']} {d['title']}", blocks=format_item_blocks(d))

    if cmd == "status":
        item = find_item_by_key(db, parsed["key"])
        if item is None:
            return _eph(f"No item `{parsed['key']}` found.")
        project = item.project
        new_status = resolve_status(project, parsed["status"])
        if new_status is None:
            valid = ", ".join(f"`{st['key']}`" for st in (project.workflow or []))
            return _eph(
                f"Unknown status `{parsed['status']}` for {project.key}. Try: done, start, review, {valid}"
            )
        old_name = status_name(project, item.status)
        if new_status == item.status:
            return _eph(f"{item_key(item)} is already *{old_name}*.")
        err = _apply_status(db, item, new_status, user)
        if err:
            return _eph(f"Couldn't update {item_key(item)}: {err}")
        db.refresh(item)
        d = item_dict(item)
        summary = f"{old_name} → {d['status_name']} by {user.name} (via Slack)"
        return _eph(f"✅ {d['key']} {old_name} → *{d['status_name']}*", blocks=format_item_blocks(d, summary))

    if cmd == "todo":
        ai = _create_todo(db, user, parsed["text"])
        if ai is None:
            return _eph("Couldn't save that action item right now.")
        return _eph(f"📝 Added to your private action items: _{_esc(parsed['text'])}_")

    if cmd == "ask":
        system = (
            "You are Hyperlane's business-analyst assistant answering from Slack. "
            f"The asker is {user.name} ({user.role}). Be concise (max ~8 lines), use Slack mrkdwn, "
            "and reference work items by key when relevant."
        )
        answer = _agent_quick(parsed["text"], system)
        if not answer:
            return _eph("The BA agent isn't available right now (no LLM provider configured).")
        return _eph(answer)

    if cmd == "standup":
        return {"text": build_standup(db, user), "response_type": "in_channel"}

    return _eph(HELP_TEXT)


def build_standup(db, user: User) -> str:
    """Yesterday / today / blockers from the user's items."""
    today = local_today()
    yesterday = today - timedelta(days=1)
    mine = (
        db.execute(select(WorkItem).where(WorkItem.assignee_id == user.id, WorkItem.is_archived.is_(False)))
        .scalars()
        .all()
    )
    done_yesterday = [it for it in mine if to_local_date(it.completed_at) == yesterday]
    worked_yesterday = [
        it
        for it in mine
        if it not in done_yesterday
        and status_category(it.project, it.status) == "in_progress"
        and to_local_date(it.updated_at) == yesterday
    ]
    today_items = [it for it in mine if status_category(it.project, it.status) == "in_progress"]
    blockers = [it for it in mine if it.blocked and status_category(it.project, it.status) != "done"]

    def lines(items: list[WorkItem], empty: str) -> str:
        if not items:
            return f"  _{empty}_"
        return "\n".join("  " + _item_line(item_dict(it)) for it in items)

    return (
        f"*Standup — {user.emoji} {user.name}* · {today.isoformat()}\n"
        f"*Yesterday*\n{lines(done_yesterday + worked_yesterday, 'nothing logged')}\n"
        f"*Today*\n{lines(today_items, 'nothing in progress yet')}\n"
        f"*Blockers*\n{lines(blockers, 'none')}"
    )


def _eph(text: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"text": text, "response_type": "ephemeral"}
    if blocks:
        out["blocks"] = blocks
    return out


# ---------------------------------------------------------------- bolt wiring (only on start())


def _build_app() -> Any:
    from slack_bolt import App

    s = get_settings()
    app = App(token=s.slack_bot_token, token_verification_enabled=False)

    @app.command("/hyperlane")
    def _slash(ack, body, respond):  # type: ignore[no-untyped-def]
        ack()
        try:
            parsed = parse_command(body.get("text"))
            with session_scope() as db:
                user = resolve_user(db, body.get("user_id"))
                result = handle_command(db, user, parsed)
            respond(**result)
        except Exception as e:
            log.exception("slash command failed")
            with suppress(Exception):
                respond(text=f"Something broke handling that command: {e.__class__.__name__}")

    @app.event("app_mention")
    def _mention(event, say):  # type: ignore[no-untyped-def]
        try:
            text = MENTION_RE.sub("", event.get("text") or "").strip()
            thread_ts = event.get("thread_ts") or event.get("ts")
            with session_scope() as db:
                user = resolve_user(db, event.get("user"))
                who = f"{user.name} ({user.role})" if user else "an unlinked Slack user"
            system = (
                "You are Hyperlane's business-analyst assistant, mentioned in Slack by "
                f"{who}. Be concise, use Slack mrkdwn, reference work items by key."
            )
            answer = _agent_quick(text or "Hello?", system) or (
                "The BA agent isn't available right now (no LLM provider configured)."
            )
            post_message(
                event.get("channel"),
                answer,
                thread_ts=thread_ts,
                kind="agent_reply",
                entity_type="slack_thread",
            )
        except Exception:
            log.exception("app_mention handler failed")

    @app.event("message")
    def _message(event, logger):  # type: ignore[no-untyped-def]
        try:
            if event.get("bot_id") or event.get("subtype"):
                return
            thread_ts = event.get("thread_ts")
            ts = event.get("ts")
            if not thread_ts or thread_ts == ts:
                return
            text = (event.get("text") or "").strip()
            if not text:
                return
            with session_scope() as db:
                item = item_for_thread_ts(db, thread_ts)
                if item is None:
                    return
                user = resolve_user(db, event.get("user"))
                name = None if user else (slack_display_name(event.get("user")) or "Slack user")
                add_slack_comment(db, item, text, author=user, author_name=name, external_ref=ts)
                log.info("slack thread reply -> comment on %s", item_key(item))
        except Exception:
            log.exception("message handler failed")

    @app.action("open_item")
    def _open(ack):  # type: ignore[no-untyped-def]
        ack()

    return app


def start() -> bool:
    """Start the Socket Mode handler in a daemon thread. Returns True if started."""
    global _bolt_app, _handler, _thread, _last_error
    s = get_settings()
    if not s.slack_enabled:
        return False
    if _thread is not None and _thread.is_alive():
        return True
    try:
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        _bolt_app = _build_app()
        _handler = SocketModeHandler(_bolt_app, s.slack_app_token)
    except Exception as e:  # noqa: BLE001 - slack-bolt raises plain errors on bad tokens
        _last_error = f"could not build Slack app: {e}"
        log.error(_last_error)
        return False

    def _run() -> None:
        global _connected, _last_error
        try:
            _connected = True
            _handler.start()  # blocks until close()
        except Exception as e:  # noqa: BLE001 - socket-mode thread must die quietly
            _last_error = str(e)
            log.error("slack socket mode stopped: %s", e)
        finally:
            _connected = False

    _thread = threading.Thread(target=_run, name="hyperlane-slack", daemon=True)
    _thread.start()
    log.info("slack socket mode handler started")
    return True


def stop() -> None:
    global _handler, _thread, _connected
    if _handler is not None:
        with suppress(Exception):
            _handler.close()
    _handler = None
    _thread = None
    _connected = False


def status() -> dict[str, Any]:
    s = get_settings()
    enabled = s.slack_enabled
    if not s.slack_bot_token and not s.slack_app_token:
        detail = "not configured (SLACK_BOT_TOKEN + SLACK_APP_TOKEN)"
    elif not enabled:
        detail = "partially configured: need both SLACK_BOT_TOKEN and SLACK_APP_TOKEN"
    elif _connected:
        detail = "socket mode connected"
    else:
        detail = _last_error or "socket mode not running"
    return {
        "enabled": enabled,
        "connected": bool(_connected),
        "channel": s.slack_default_channel,
        "detail": detail,
    }
