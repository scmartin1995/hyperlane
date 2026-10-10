"""backend-integrations tests: no network, nothing started (test env has no tokens)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from hyperlane.config import get_settings
from hyperlane.db import session_scope, utcnow
from hyperlane.integrations import email as email_mod
from hyperlane.integrations import router, slack, teams
from hyperlane.models import Comment, IntakeMessage, IntakeRequest, NotificationLog, Project, Sprint, User, WorkItem
from hyperlane.services.events import Event
from hyperlane.services.templates import get_template

# ---------------------------------------------------------------- fixtures


@pytest.fixture()
def capture(monkeypatch):
    """Monkeypatch the outbound senders and pretend Slack + Teams are configured."""
    calls: dict[str, list] = {"slack": [], "dm": [], "teams": []}

    def fake_post_message(channel, text, *, blocks=None, thread_ts=None, **kw):
        calls["slack"].append({"channel": channel, "text": text, "blocks": blocks, "thread_ts": thread_ts, **kw})
        return f"{len(calls['slack'])}.000"

    def fake_post_dm(uid, text, *, blocks=None, **kw):
        calls["dm"].append({"user": uid, "text": text, "blocks": blocks, **kw})
        return "dm.1"

    def fake_post_card(text, title=None, facts=None, webhook=None, **kw):
        calls["teams"].append({"text": text, "title": title, "facts": facts, "webhook": webhook, **kw})
        return True

    monkeypatch.setattr(slack, "post_message", fake_post_message)
    monkeypatch.setattr(slack, "post_dm", fake_post_dm)
    monkeypatch.setattr(teams, "post_card", fake_post_card)
    s = get_settings()
    monkeypatch.setattr(s, "slack_bot_token", "xoxb-test")
    monkeypatch.setattr(s, "slack_default_channel", "#updates")
    monkeypatch.setattr(s, "teams_webhook_url", "https://example.invalid/webhook")
    return calls


@pytest.fixture()
def world(client):
    """A project + two users + items + sprint, inserted directly (core API may not exist yet)."""
    tpl = get_template("software-scrum")
    sfx = uuid.uuid4().hex[:6]
    with session_scope() as db:
        alice = User(name="Alice Ng", handle=f"alice-{sfx}", email=f"alice-{sfx}@example.com", slack_user_id=f"UA{sfx}",
                     preferences={"slack_dm": True, "notify_assignments": True})
        bob = User(name="Bob Ray", handle=f"bob-{sfx}", email=f"bob-{sfx}@example.com", slack_user_id=f"UB{sfx}",
                   preferences={"slack_dm": False})
        db.add_all([alice, bob])
        db.flush()
        proj = Project(key=f"I{sfx[:4].upper()}", name="Integration Test", item_types=tpl["item_types"], workflow=tpl["workflow"],
                       settings=tpl["settings"], slack_channel="#int-updates")
        db.add(proj)
        db.flush()
        sprint = Sprint(project_id=proj.id, number=1, name="Sprint 1", goal="Ship it",
                        start_date=date.today(), end_date=date.today() + timedelta(days=13), state="active",
                        committed_points=21, committed_count=4, completed_points=13, completed_count=3)
        db.add(sprint)
        items = [
            WorkItem(project_id=proj.id, number=1, title="Build the thing", status="in_progress", assignee_id=alice.id, points=5),
            WorkItem(project_id=proj.id, number=2, title="Fix the bug", status="ready", assignee_id=alice.id,
                     due_date=date.today() - timedelta(days=2)),
            WorkItem(project_id=proj.id, number=3, title="Old win", status="done", assignee_id=bob.id,
                     completed_at=utcnow() - timedelta(days=1)),
            WorkItem(project_id=proj.id, number=4, title="Stuck", status="in_progress", blocked=True, blocked_reason="waiting on API"),
        ]
        db.add_all(items)
        db.flush()
        ids = {"project": proj.id, "alice": alice.id, "bob": bob.id, "sprint": sprint.id, "items": [i.id for i in items],
               "key": proj.key, "alice_slack": alice.slack_user_id}
    return ids


# ---------------------------------------------------------------- email.parse_message

PLAIN = b"""From: Jane Doe <jane@example.com>
To: requests@hyperlane.local
Subject: Need a CSV export
Message-ID: <abc123@example.com>
Date: Mon, 06 Oct 2025 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

Hi team,

We need a CSV export of the dashboard.

Thanks,
Jane
"""

HTML_ONLY = b"""From: =?utf-8?q?Ren=C3=A9?= <rene@example.com>
Subject: =?utf-8?q?R=C3=A9sum=C3=A9_of_the_request?=
Message-ID: <html-1@example.com>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="XX"

--XX
Content-Type: text/html; charset=utf-8

<html><head><style>p{color:red}</style><title>ignored</title></head>
<body><p>Hello &amp; welcome,</p><div>Please add <b>dark mode</b>.</div><script>alert(1)</script></body></html>
--XX--
"""

REPLY = b"""From: jane@example.com
Subject: Re: Need a CSV export
Message-ID: <reply-1@example.com>
In-Reply-To: <out-1@hyperlane.local>
References: <abc123@example.com> <out-1@hyperlane.local>
Content-Type: text/plain

Yes, weekly is fine.
"""


def test_parse_plain_message():
    p = email_mod.parse_message(PLAIN)
    assert p["subject"] == "Need a CSV export"
    assert p["from_name"] == "Jane Doe"
    assert p["from_addr"] == "jane@example.com"
    assert p["message_id"] == "<abc123@example.com>"
    assert p["in_reply_to"] is None and p["references"] == []
    assert p["body"].startswith("Hi team,") and "CSV export" in p["body"]
    assert p["date"] is not None and p["date"].year == 2025


def test_parse_html_only_multipart_strips_tags_and_decodes_headers():
    p = email_mod.parse_message(HTML_ONLY)
    assert p["subject"] == "Résumé of the request"
    assert p["from_name"] == "René"
    assert "<" not in p["body"] and "alert" not in p["body"] and "color:red" not in p["body"]
    assert "Hello & welcome," in p["body"]
    assert "Please add dark mode." in p["body"]


def test_parse_reply_threading_headers():
    p = email_mod.parse_message(REPLY)
    assert p["in_reply_to"] == "<out-1@hyperlane.local>"
    assert p["references"] == ["<abc123@example.com>", "<out-1@hyperlane.local>"]
    assert p["from_name"] == "jane"  # derived from the address when no display name
    assert email_mod.parse_message(b"garbage")["subject"] == "(no subject)"


def test_strip_html_blocks_to_newlines():
    assert email_mod.strip_html("<p>one</p><p>two</p>") == "one\n\ntwo"


# ---------------------------------------------------------------- email ingest (DB, no IMAP)


def test_email_ingest_creates_request_then_threads_reply_and_dedupes(client):
    p = email_mod.parse_message(PLAIN)
    rid = email_mod.ingest(p)
    assert rid
    assert email_mod.ingest(p) is None  # same Message-ID -> skipped
    with session_scope() as db:
        req = db.get(IntakeRequest, rid)
        assert req.channel == "email" and req.thread_key == "<abc123@example.com>"
        assert req.state in ("new", "clarifying", "ready")  # agent.analyze may have advanced it
        assert req.requester_email == "jane@example.com" and req.requester_name == "Jane Doe"
        assert len(req.messages) == 1 and req.messages[0].direction == "inbound"
    reply_id = email_mod.ingest(email_mod.parse_message(REPLY))
    assert reply_id == rid
    with session_scope() as db:
        msgs = db.query(IntakeMessage).filter_by(request_id=rid).order_by(IntakeMessage.created_at).all()
        assert [m.direction for m in msgs] == ["inbound", "inbound"]
        assert msgs[-1].external_ref == "<reply-1@example.com>" and "weekly" in msgs[-1].body
        assert db.get(IntakeRequest, rid).state != "new"


def test_send_reply_noop_when_unconfigured(client):
    with session_scope() as db:
        req = IntakeRequest(subject="x", original_body="y", requester_email="a@b.c", thread_key="<k@b.c>")
        db.add(req)
        db.flush()
        assert email_mod.send_reply(req, "hello") is None
    assert email_mod.poll_inbox() == 0


# ---------------------------------------------------------------- slash commands


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", {"cmd": "help"}),
        ("help", {"cmd": "help"}),
        ("mine", {"cmd": "mine"}),
        ("standup", {"cmd": "standup"}),
        ("todo call the vendor", {"cmd": "todo", "text": "call the vendor"}),
        ("ask what is blocked?", {"cmd": "ask", "text": "what is blocked?"}),
        ("hl-12 done", {"cmd": "status", "key": "HL-12", "status": "done", "text": "done"}),
        ("HL-007 start", {"cmd": "status", "key": "HL-7", "status": "start", "text": "start"}),
        ("HL-3 In Review", {"cmd": "status", "key": "HL-3", "status": "in", "text": "In Review"}),
        ("HL-3", {"cmd": "show", "key": "HL-3"}),
        ("todo", {"cmd": "error", "text": "Usage: `/hyperlane todo <text>`"}),
        ("frobnicate", {"cmd": "unknown", "text": "frobnicate"}),
    ],
)
def test_parse_command(text, expected):
    assert slack.parse_command(text) == expected


def test_resolve_status_aliases():
    proj = Project(key="X", name="x", workflow=get_template("software-scrum")["workflow"])
    assert slack.resolve_status(proj, "done") == "done"
    assert slack.resolve_status(proj, "start") == "in_progress"
    assert slack.resolve_status(proj, "review") == "review"
    assert slack.resolve_status(proj, "In Review") == "review"
    assert slack.resolve_status(proj, "backlog") == "backlog"
    assert slack.resolve_status(proj, "nope") is None
    kanban = Project(key="K", name="k", workflow=get_template("product-discovery")["workflow"])
    assert slack.resolve_status(kanban, "done") == "learned"
    assert slack.resolve_status(kanban, "start") == "running"


def test_handle_command_requires_linked_user(client):
    with session_scope() as db:
        out = slack.handle_command(db, None, slack.parse_command("mine"))
    assert "Link your profile" in out["text"] and out["response_type"] == "ephemeral"
    with session_scope() as db:
        assert "Hyperlane commands" in slack.handle_command(db, None, slack.parse_command(""))["text"]


def test_handle_command_mine_show_todo_standup(world):
    with session_scope() as db:
        alice = db.get(User, world["alice"])
        mine = slack.handle_command(db, alice, slack.parse_command("mine"))
        k = world["key"]
        assert f"{k}-1" in mine["text"] and f"{k}-2" in mine["text"] and f"{k}-3" not in mine["text"]
        assert f"In Progress ({k})" in mine["text"]

        show = slack.handle_command(db, alice, slack.parse_command(f"{k}-1"))
        assert show["blocks"][0]["text"]["text"].startswith("*<http://")
        assert slack.handle_command(db, alice, slack.parse_command(f"{k}-99"))["text"].startswith("No item")

        todo = slack.handle_command(db, alice, slack.parse_command("todo buy coffee"))
        assert "buy coffee" in todo["text"] and todo["response_type"] == "ephemeral"

        standup = slack.handle_command(db, alice, slack.parse_command("standup"))
        assert standup["response_type"] == "in_channel"
        assert "*Today*" in standup["text"] and f"{k}-1" in standup["text"]

        same = slack.handle_command(db, alice, slack.parse_command(f"{k}-1 start"))
        assert "already" in same["text"]
        bad = slack.handle_command(db, alice, slack.parse_command(f"{k}-1 warp"))
        assert "Unknown status" in bad["text"]


def test_resolve_user_by_slack_id_without_network(world):
    with session_scope() as db:
        assert slack.resolve_user(db, world["alice_slack"], lookup_email=False).id == world["alice"]
        assert slack.resolve_user(db, "U0NOBODY", lookup_email=False) is None
        assert slack.resolve_user(db, "U0NOBODY") is None  # no client configured -> None, no network


# ---------------------------------------------------------------- block kit


def test_format_item_blocks_structure():
    item = {"id": "abc", "key": "HL-12", "title": "Tune <engine> & go", "status": "in_progress",
            "status_name": "In Progress", "category": "in_progress", "assignee_name": "Alice", "priority": "high",
            "points": 5, "url": "http://localhost:8787/items/abc"}
    blocks = slack.format_item_blocks(item, "Ready → In Progress by Bob")
    assert [b["type"] for b in blocks] == ["section", "section", "context", "actions"]
    assert blocks[0]["text"]["text"] == "*<http://localhost:8787/items/abc|HL-12>* Tune &lt;engine&gt; &amp; go"
    fields = {f["text"].split("\n")[0]: f["text"].split("\n")[1] for f in blocks[1]["fields"]}
    assert fields == {"*Status*": "🔄 In Progress", "*Assignee*": "Alice", "*Priority*": "high", "*Points*": "5"}
    assert blocks[2]["elements"][0]["text"] == "Ready → In Progress by Bob"
    assert blocks[3]["elements"][0]["url"] == "http://localhost:8787/items/abc"
    assert [b["type"] for b in slack.format_item_blocks({"key": "X-1", "title": "t"})] == ["section", "section", "actions"]


def test_teams_card_builders():
    ad = teams.build_adaptive_card("body", "Title", [("A", "1")])
    content = ad["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard" and content["body"][0]["text"] == "Title"
    assert content["body"][2]["facts"] == [{"title": "A", "value": "1"}]
    mc = teams.build_message_card("body", "Title", [("A", "1")])
    assert mc["@type"] == "MessageCard" and mc["sections"][0]["facts"][0]["name"] == "A"
    assert teams.post_card("x") is False  # unconfigured -> no network, False


# ---------------------------------------------------------------- router decisions


def test_router_ignores_irrelevant_events(world, capture):
    router.process(Event(type="work_item.updated", entity_id=world["items"][0], data={"changes": {"title": ["a", "b"]}}))
    router.process(Event(type="work_item.moved", entity_id=world["items"][0], data={"changes": {"rank": [1, 2]}}))
    router.process(Event(type="intake.updated", entity_id="nope"))
    router.process(Event(type="notification.sent", entity_id="nope"))
    assert capture == {"slack": [], "dm": [], "teams": []}


def test_router_status_change_posts_blocks_then_threads(world, capture):
    item_id = world["items"][0]
    ev = Event(type="work_item.updated", project_id=world["project"], entity_type="work_item", entity_id=item_id,
               actor_id=world["bob"], data={"changes": {"status": ["ready", "in_progress"]}})
    router.process(ev)
    assert len(capture["slack"]) == 1
    first = capture["slack"][0]
    assert first["channel"] == "#int-updates"  # project override wins over SLACK_DEFAULT_CHANNEL
    assert first["thread_ts"] is None and first["blocks"] and first["kind"] == "item_update"
    assert "Ready → *In Progress* by Bob Ray" in first["text"] and f"{world['key']}-1" in first["text"]
    assert len(capture["teams"]) == 1 and ("Status", "Ready → In Progress") in capture["teams"][0]["facts"]
    assert capture["teams"][0]["webhook"] == "https://example.invalid/webhook"

    # simulate the first message having been logged (the real post_message does this)
    with session_scope() as db:
        db.add(NotificationLog(channel="slack", target="#int-updates", kind="item_update", entity_type="work_item",
                               entity_id=item_id, body="x", ok=True, external_ref="1700.001"))
    router.process(Event(type="work_item.moved", entity_id=item_id, actor_id=world["bob"],
                         data={"from_status": "in_progress", "to_status": "review"}))
    second = capture["slack"][1]
    assert second["thread_ts"] == "1700.001" and second["blocks"] is None
    assert "*In Review*" in second["text"]
    assert slack.item_thread_ts(item_id) == "1700.001"


def test_router_assignment_dm_respects_preferences(world, capture):
    item_id = world["items"][1]
    # assign to Alice (opted in) by Bob -> DM
    router.process(Event(type="work_item.updated", entity_id=item_id, actor_id=world["bob"],
                         data={"changes": {"assignee_id": [None, world["alice"]]}}))
    assert len(capture["dm"]) == 1 and capture["dm"][0]["user"] == world["alice_slack"]
    assert capture["dm"][0]["kind"] == "assignment"
    assert "assigned to *Alice Ng*" in capture["slack"][-1]["text"]
    # assign to Bob (slack_dm false) -> channel post but no DM
    router.process(Event(type="work_item.updated", entity_id=item_id, actor_id=world["alice"],
                         data={"changes": {"assignee_id": [world["alice"], world["bob"]]}}))
    assert len(capture["dm"]) == 1
    # self-assignment -> no DM
    router.process(Event(type="work_item.updated", entity_id=item_id, actor_id=world["alice"],
                         data={"changes": {"assignee_id": [world["bob"], world["alice"]]}}))
    assert len(capture["dm"]) == 1


def test_router_blocked_flag(world, capture):
    router.process(Event(type="work_item.updated", entity_id=world["items"][3],
                         data={"changes": {"blocked": [False, True]}}))
    assert "⛔ *blocked* (waiting on API)" in capture["slack"][0]["text"]


def test_router_comment_skips_slack_source_and_threads_web_comments(world, capture):
    item_id = world["items"][0]
    with session_scope() as db:
        web = Comment(work_item_id=item_id, author_id=world["alice"], body="Looks good to me", source="web")
        from_slack = Comment(work_item_id=item_id, author_name="Someone", body="echo?", source="slack")
        db.add_all([web, from_slack])
        db.flush()
        web_id, slack_id = web.id, from_slack.id
    router.process(Event(type="comment.created", entity_id=slack_id, data={"source": "slack"}))
    assert capture["slack"] == []
    router.process(Event(type="comment.created", entity_id=web_id))  # source looked up from the row
    assert len(capture["slack"]) == 1
    assert "Alice Ng" in capture["slack"][0]["text"] and "Looks good" in capture["slack"][0]["text"]
    assert capture["teams"][0]["title"].startswith(f"Alice Ng commented on {world['key']}-1")


def test_router_sprint_summaries(world, capture):
    router.process(Event(type="sprint.started", entity_id=world["sprint"]))
    router.process(Event(type="sprint.closed", entity_id=world["sprint"], data={"carried": 1}))
    start, close = capture["slack"]
    assert "Sprint 1 started" in start["text"] and "Goal: Ship it" in start["text"] and "21 pts" in start["text"]
    assert start["kind"] == "sprint_start" and start["entity_type"] == "sprint"
    assert "Sprint 1 closed" in close["text"] and "13 / 21 pts (62%)" in close["text"]
    assert "Carried over: 1" in close["text"] and close["kind"] == "sprint_close"
    assert [c["kind"] for c in capture["teams"]] == ["sprint_start", "sprint_close"]


def test_router_handle_never_raises_and_is_quiet_when_unconfigured(client):
    router.handle(Event(type="work_item.updated", entity_id=None, data=None))  # type: ignore[arg-type]
    router.handle(Event(type="sprint.started"))
    router.process(Event(type="work_item.updated", entity_id="missing", data={"changes": {"status": ["a", "b"]}}))


def test_daily_digest(world, capture):
    sent = router.daily_digest()
    k = world["key"]
    assert sent["projects"] >= 1 and sent["dms"] >= 1
    digest = next(c for c in capture["slack"] if c["kind"] == "digest" and f"{k}-3" in c["text"])
    assert "Done yesterday" in digest["text"] and digest["channel"] == "#int-updates"
    assert f"{k}-1" in digest["text"] and f"{k}-4" in digest["text"]
    dm = next(d for d in capture["dm"] if d["user"] == world["alice_slack"])
    assert f"{k}-1" in dm["text"] and "*Overdue* (1)" in dm["text"]
    assert "buy coffee" not in dm["text"]  # private contents never leave the machine


# ---------------------------------------------------------------- api


def test_integrations_status_all_disabled(client):
    r = client.get("/api/integrations/status")
    assert r.status_code == 200
    body = r.json()
    assert body["slack"] == {"enabled": False, "connected": False, "channel": None,
                             "detail": "not configured (SLACK_BOT_TOKEN + SLACK_APP_TOKEN)"}
    assert body["teams"]["enabled"] is False
    assert body["email"]["enabled"] is False and body["email"]["last_poll"] is None
    for which in ("slack", "teams", "email"):
        t = client.post(f"/api/integrations/test/{which}").json()
        assert t["ok"] is False and "not" in t["detail"]


def test_notifications_log_and_send(client, user):
    with session_scope() as db:
        db.add(NotificationLog(channel="teams", target="https://t/…", kind="test", body="hi", ok=False, error="boom"))
    log = client.get("/api/notifications/log?limit=5").json()
    assert log and {"id", "channel", "kind", "body", "ok", "error", "created_at"} <= set(log[0])
    assert len(log) <= 5
    r = client.post("/api/notifications/send", json={"channel": "slack", "text": "hello"})
    assert r.status_code == 400 and "not configured" in r.json()["detail"]
    r = client.post("/api/notifications/send", json={"channel": "teams", "text": "  "})
    assert r.status_code == 400


def test_notifications_send_requires_login(client):
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.post("/api/notifications/send", json={"channel": "slack", "text": "x"}).status_code == 401
