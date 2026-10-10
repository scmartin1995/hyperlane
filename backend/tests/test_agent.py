"""Agent slice tests. conftest sets HYPERLANE_LLM_PROVIDER=none -> deterministic StubProvider."""

from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import select


@pytest.fixture()
def project(client):
    """A user + software-scrum project created straight through the ORM (no dependency on backend-core)."""
    from hyperlane.db import get_sessionmaker
    from hyperlane.models import Project, User
    from hyperlane.services.templates import get_template

    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.handle == "agent-tester"))
        if user is None:
            user = User(name="Agent Tester", handle="agent-tester", role="po", email="agent@test.local")
            db.add(user)
            db.flush()
        proj = db.scalar(select(Project).where(Project.key == "AGT"))
        if proj is None:
            tpl = get_template("software-scrum")
            proj = Project(
                key="AGT",
                name="Agent Test Project",
                template="software-scrum",
                methodology=tpl["methodology"],
                item_types=tpl["item_types"],
                workflow=tpl["workflow"],
                settings=tpl["settings"],
                lead_id=user.id,
            )
            db.add(proj)
        db.commit()
        ids = {"user_id": user.id, "project_id": proj.id}
    client.post("/api/auth/login", json={"user_id": ids["user_id"]})
    return ids


def _sse_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload and payload != "{}":
                events.append(json.loads(payload))
    return events


def test_agent_status(client, project):
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "none" and body["available"] is False and body["model"]


def test_chat_thread_stream(client, project):
    r = client.post("/api/chat/threads", json={"project_id": project["project_id"], "mode": "analyst"})
    assert r.status_code == 201, r.text
    thread = r.json()
    assert thread["title"] == "New conversation"

    with client.stream(
        "POST", f"/api/chat/threads/{thread['id']}/messages", json={"content": "What should we build first?"}
    ) as resp:
        assert resp.status_code == 200
        events = _sse_events(resp)
    types = [e["type"] for e in events]
    assert "text" in types and types[-1] == "done"
    assert any(e["type"] == "tool_call" and e["name"] == "search_items" for e in events)
    assert any(e["type"] == "tool_result" and e["name"] == "search_items" for e in events)
    msg_ev = next(e for e in events if e["type"] == "message")
    assert msg_ev["message"]["role"] == "assistant"
    assert "".join(e["delta"] for e in events if e["type"] == "text") == msg_ev["message"]["content"]

    full = client.get(f"/api/chat/threads/{thread['id']}").json()
    assert full["title"] == "What should we build first?"
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert full["messages"][1]["tool_calls"][0]["name"] == "search_items"

    # second turn replays the tool exchange from ChatMessage.raw without breaking
    with client.stream("POST", f"/api/chat/threads/{thread['id']}/messages", json={"content": "And then?"}) as resp:
        events2 = _sse_events(resp)
    assert events2[-1]["type"] == "done"
    assert len(client.get(f"/api/chat/threads/{thread['id']}").json()["messages"]) == 4

    mine = client.get("/api/chat/threads").json()
    assert any(t["id"] == thread["id"] for t in mine)
    assert client.delete(f"/api/chat/threads/{thread['id']}").status_code == 204
    assert client.get(f"/api/chat/threads/{thread['id']}").status_code == 404


def test_intake_clarify_then_ready_then_convert(client, project):
    r = client.post(
        "/api/intake",
        json={
            "subject": "Export ticket history to CSV",
            "body": "Could we get an export button on the results page?",
            "requester_name": "Sam Stakeholder",
            "requester_email": "sam@example.com",
            "project_id": project["project_id"],
        },
    )
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["state"] == "clarifying"
    assert req["questions_asked"] == 1
    outbound = [m for m in req["messages"] if m["direction"] == "outbound"]
    assert len(outbound) == 1 and outbound[0]["author"] == "Hyperlane Agent"
    assert "1." in outbound[0]["body"]  # numbered questions
    assert req["requirements"]["confidence"] < 0.75

    r = client.post(
        f"/api/intake/{req['id']}/messages",
        json={"body": "Success = a support lead can download a CSV per month. Users: support leads.", "direction": "inbound"},
    )
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["state"] == "ready"
    assert req["questions_asked"] == 1  # no second question needed
    assert req["requirements"]["proposed_items"]
    assert req["summary"]

    r = client.post(f"/api/intake/{req['id']}/convert", json={"project_id": project["project_id"]})
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1 and items[0]["key"].startswith("AGT-")
    assert items[0]["source_ref"] == req["id"]
    req = client.get(f"/api/intake/{req['id']}").json()
    assert req["state"] == "converted" and req["converted_item_ids"] == [items[0]["id"]]
    assert client.get("/api/intake?state=converted").json()[0]["id"] == req["id"]


def test_intake_max_questions_marks_needs_human(client, project):
    r = client.post("/api/intake", json={"subject": "Thing", "body": "pls", "project_id": project["project_id"]})
    req = r.json()
    client.patch(f"/api/intake/{req['id']}", json={"max_questions": 1})
    # the stub stays unsure until the requester replies; with max_questions=1 analyze must stop asking
    r = client.post(f"/api/intake/{req['id']}/analyze")
    assert r.status_code == 200
    body = r.json()
    assert body["questions_asked"] == 1
    assert body["state"] == "ready" and body["needs_human"] is True


def test_excel_import_preview_and_commit(client, project):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Backlog"
    ws.append(["Epic", "Feature", "Summary", "Issue Type", "Status", "Story Points", "Assignee", "Labels", "Due"])
    ws.append(["Reporting", "Exports", "As an admin I can export my invoices", "Story", "To Do", 3, "Agent Tester", "frontend", "2026-11-01"])
    ws.append(["Reporting", "Exports", "Exports API", "Story", "In Progress", 5, "Nobody Known", "backend;api", None])
    ws.append(["Reporting", None, "Export total wrong after refund", "Bug", "Done", 2, None, None, None])
    ws.append([None, None, None, None, None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(
        f"/api/projects/{project['project_id']}/import/excel/preview",
        files={"file": ("backlog.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["sheets"] == ["Backlog"] and preview["sheet"] == "Backlog"
    assert preview["total_rows"] == 3 and len(preview["rows"]) == 3
    m = preview["mapping"]
    assert m["title"] == "Summary" and m["epic"] == "Epic" and m["feature"] == "Feature"
    assert m["type"] == "Issue Type" and m["status"] == "Status" and m["points"] == "Story Points"
    assert m["assignee"] == "Assignee" and m["labels"] == "Labels" and m["due_date"] == "Due"

    r = client.post(
        f"/api/projects/{project['project_id']}/import/excel/commit",
        json={"file_token": preview["file_token"], "sheet": "Backlog", "mapping": m, "create_missing_users": False},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    created = {it["title"]: it for it in out["created"]}
    assert out["skipped"] == 0
    assert any("Nobody Known" in w for w in out["warnings"])
    epic, feature = created["Reporting"], created["Exports"]
    assert epic["type"] == "epic" and epic["parent_id"] is None
    assert feature["type"] == "feature" and feature["parent_id"] == epic["id"]
    story = created["As an admin I can export my invoices"]
    assert story["type"] == "story" and story["parent_id"] == feature["id"]
    assert story["points"] == 3 and story["status"] == "backlog" and story["due_date"] == "2026-11-01"
    assert story["assignee_id"] == project["user_id"]
    assert [lb["name"] for lb in story["labels"]] == ["frontend"]
    api = created["Exports API"]
    assert api["status"] == "in_progress" and api["assignee_id"] is None
    assert sorted(lb["name"] for lb in api["labels"]) == ["api", "backend"]
    bug = created["Export total wrong after refund"]
    assert bug["type"] == "bug" and bug["parent_id"] == epic["id"] and bug["status"] == "done"
    assert all(it["source"] == "excel" for it in out["created"])

    # csv works too and is re-importable (epic deduped against existing items)
    csv_bytes = b"Summary,Epic,Priority\nScheduled export emails,Reporting,P1\n"
    r = client.post(
        f"/api/projects/{project['project_id']}/import/excel/preview",
        files={"file": ("more.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    p2 = r.json()
    assert p2["mapping"]["title"] == "Summary" and p2["mapping"]["priority"] == "Priority"
    r = client.post(
        f"/api/projects/{project['project_id']}/import/excel/commit",
        json={"file_token": p2["file_token"], "mapping": p2["mapping"]},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["created"]
    assert len(rows) == 1 and rows[0]["parent_id"] == epic["id"] and rows[0]["priority"] == "critical"


def test_backlog_generate_and_apply(client, project):
    pid = project["project_id"]
    r = client.post(f"/api/projects/{pid}/backlog/generate", json={"prompt": "Live status dashboard for the support team"})
    assert r.status_code == 200, r.text
    proposal = r.json()
    assert proposal["summary"] and proposal["questions"] == []
    types = [it["type"] for it in proposal["items"]]
    assert types[0] == "epic" and "feature" in types and "story" in types
    temp_ids = {it["temp_id"] for it in proposal["items"]}
    assert all(it["parent_temp_id"] in temp_ids for it in proposal["items"] if it["parent_temp_id"])
    assert all(it["points"] is None for it in proposal["items"] if it["type"] != "story")

    thin = client.post(f"/api/projects/{pid}/backlog/generate", json={"prompt": "stuff"}).json()
    assert thin["questions"]

    r = client.post(f"/api/projects/{pid}/backlog/apply", json={"items": proposal["items"]})
    assert r.status_code == 200, r.text
    created = r.json()
    assert len(created) == len(proposal["items"])
    by_title = {it["title"]: it for it in created}
    epic = next(it for it in created if it["type"] == "epic")
    feature = next(it for it in created if it["type"] == "feature")
    assert feature["parent_id"] == epic["id"]
    stories = [it for it in created if it["type"] == "story"]
    assert stories and all(s["parent_id"] == feature["id"] for s in stories)
    assert all(it["source"] == "agent" for it in created)
    assert by_title[epic["title"]]["key"].startswith("AGT-")

    # TODO(backend-core): once services.items.bulk_create lands, this exercises it instead of the agent fallback.
    try:
        from hyperlane.services.items import bulk_create  # noqa: F401
    except ImportError:
        pass


def test_sync_helpers_without_provider(project):
    from hyperlane import agent

    assert agent.quick("Say hi in five words").startswith("(agent offline)")
    summary = agent.summarize_retro(
        {"went_well": [{"text": "Fast reviews"}], "improve": [{"text": "Fewer handoffs"}], "kudos": [], "actions": [], "mood": {"u1": 4}},
        {"committed_points": 20, "completed_points": 15},
    )
    assert "15" in summary and "Fast reviews" in summary
    notes = agent.draft_capacity_insight({"sprints_observed": 3, "avg_points": 10, "commitment_accuracy": 0.6, "stddev_points": 1})
    assert notes and "over-commit" in notes[0]
    assert agent.draft_capacity_insight({"sprints_observed": 1})[0].startswith("Too early")


def test_tool_registry_executes_in_own_session(project):
    from hyperlane.agent.tools import REGISTRY, available_tools, execute

    names = {t.name for t in available_tools(slack=False)}
    assert "send_slack_message" not in names
    assert "send_slack_message" in {t.name for t in available_tools(slack=True)}
    for required in ("list_projects", "search_items", "list_items", "get_item", "create_items", "update_item",
                     "add_comment", "list_sprints", "sprint_summary", "plan_suggestion", "list_people", "capacity",
                     "metrics_overview", "evm_report", "forecast", "create_action_item", "list_my_action_items",
                     "create_intake_request"):
        assert required in names, required

    out = execute(REGISTRY["list_projects"], project["user_id"], {})
    assert out.ok and any(p["key"] == "AGT" for p in out.result)

    out = execute(REGISTRY["create_action_item"], project["user_id"], {"title": "Check tyre pressures", "due_date": "2026-10-12"})
    assert out.ok and out.result["id"]
    mine = execute(REGISTRY["list_my_action_items"], project["user_id"], {})
    assert any(a["title"] == "Check tyre pressures" for a in mine.result)

    # analytics tools degrade gracefully until that slice lands
    out = execute(REGISTRY["metrics_overview"], project["user_id"], {"project_id": project["project_id"]})
    assert out.ok or "not available" in out.summary
    bad = execute(REGISTRY["get_item"], project["user_id"], {"id_or_key": "AGT-99999"})
    assert not bad.ok and "not found" in bad.summary
