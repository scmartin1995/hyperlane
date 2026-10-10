"""Requests surface in the backlog as items needing triage."""

from datetime import date, timedelta


def _login_any(client):
    users = client.get("/api/users").json()
    u = users[0] if users else client.post("/api/users", json={"name": "Triage Tester"}).json()
    client.post("/api/auth/login", json={"user_id": u["id"]})
    return u


def _project(client):
    projects = client.get("/api/projects").json()
    if projects:
        return projects[0]
    return client.post("/api/projects", json={"name": "Triage Proj", "template": "software-scrum"}).json()


def test_request_becomes_backlog_item_and_mirrors_thread(client):
    _login_any(client)
    proj = _project(client)
    req = client.post("/api/intake", json={"subject": f"[{proj['key']}] Need a leaderboard", "body": "Office tournament next month, want a leaderboard."}).json()
    assert req["work_item_id"], "a backlog item is created immediately"
    item = client.get(f"/api/items/{req['work_item_id']}").json()
    assert item["project_id"] == proj["id"]
    assert item["title"] == "Need a leaderboard"  # routing tag stripped
    assert "needs-triage" in [label["name"] for label in item["labels"]]
    meta = item["custom"]["intake"]
    assert meta["request_id"] == req["id"] and meta["state"] in ("clarifying", "ready", "new")
    assert "Request from" in item["description"]
    # the assistant's clarifying question (stub provider asks one) shows up in the discussion
    if req["state"] == "clarifying":
        assert any(c["source"] == "agent" for c in item["comments"])
    # triage list has it
    tri = client.get(f"/api/projects/{proj['id']}/triage").json()
    assert any(t["id"] == item["id"] for t in tri)
    # requester replies → mirrored as a comment, re-analysed
    client.post(f"/api/intake/{req['id']}/messages", json={"body": "Top 10 by best lap, resets weekly.", "direction": "inbound"})
    item = client.get(f"/api/items/{item['id']}").json()
    assert any("Top 10" in c["body"] for c in item["comments"])


def test_accept_escalate_decline_snooze(client):
    _login_any(client)
    proj = _project(client)
    mk = lambda subj: client.post("/api/intake", json={"subject": subj, "body": "please", "project_id": proj["id"]}).json()  # noqa: E731
    # accept
    r1 = mk("Accept me")
    out = client.post(f"/api/items/{r1['work_item_id']}/triage", json={"action": "accept", "type": "story"}).json()
    assert out["item"]["type"] == "story"
    assert "needs-triage" not in [label["name"] for label in out["item"]["labels"]]
    assert out["item"]["custom"]["intake"]["state"] == "accepted"
    assert client.get(f"/api/intake/{r1['id']}").json()["state"] == "converted"
    assert all(t["id"] != r1["work_item_id"] for t in client.get(f"/api/projects/{proj['id']}/triage").json())
    # decline → archived
    r2 = mk("Decline me")
    client.post(f"/api/items/{r2['work_item_id']}/triage", json={"action": "decline", "reason": "out of scope"})
    assert client.get(f"/api/items/{r2['work_item_id']}").json()["is_archived"] is True
    assert client.get(f"/api/intake/{r2['id']}").json()["state"] == "rejected"
    # snooze → hidden when include_snoozed=false
    r3 = mk("Snooze me")
    until = (date.today() + timedelta(days=3)).isoformat()
    client.post(f"/api/items/{r3['work_item_id']}/triage", json={"action": "snooze", "until": until})
    ids = [t["id"] for t in client.get(f"/api/projects/{proj['id']}/triage?include_snoozed=false").json()]
    assert r3["work_item_id"] not in ids
    ids = [t["id"] for t in client.get(f"/api/projects/{proj['id']}/triage").json()]
    assert r3["work_item_id"] in ids
    # escalate → in the active sprint (create + start one if needed)
    sprints = client.get(f"/api/projects/{proj['id']}/sprints?state=active").json()
    if not sprints:
        sp = client.post(f"/api/projects/{proj['id']}/sprints", json={}).json()
        client.post(f"/api/sprints/{sp['id']}/start")
        sprints = [sp]
    r4 = mk("Escalate me")
    out = client.post(f"/api/items/{r4['work_item_id']}/triage", json={"action": "escalate"}).json()
    moved = out["created"] or [out["item"]]
    assert all(m["sprint_id"] == sprints[0]["id"] for m in moved)
    # message requester (no email configured → stored only) shows as a comment
    r5 = mk("Chat with me")
    client.post(f"/api/items/{r5['work_item_id']}/message-requester", json={"body": "Can you share a mockup?"})
    item = client.get(f"/api/items/{r5['work_item_id']}").json()
    assert any("mockup" in c["body"] for c in item["comments"])
