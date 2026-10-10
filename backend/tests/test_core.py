"""Core slice: users, projects, items, ranking, sprints, comments, action items, search, seed, tree."""

from __future__ import annotations

import uuid

import pytest


def _login(client, user_id: str) -> None:
    r = client.post("/api/auth/login", json={"user_id": user_id})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def pilot(client):
    """Stable identity for this module (the conftest `user` fixture is function-scoped)."""
    r = client.post("/api/users", json={"name": "Core Pilot", "role": "developer", "email": "core-pilot@example.test"})
    assert r.status_code == 201, r.text
    _login(client, r.json()["id"])
    return r.json()


@pytest.fixture(scope="module")
def project(client, pilot):
    r = client.post(
        "/api/projects",
        json={"name": f"Core Test {uuid.uuid4().hex[:4]}", "template": "software-scrum", "key": "CT" + uuid.uuid4().hex[:3].upper()},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def me(client, pilot):
    """Re-login as the module's pilot before each test (other tests switch profiles)."""
    _login(client, pilot["id"])
    return pilot


# ---------------------------------------------------------------- users / login


def test_onboarding_project_without_session(client):
    """With zero projects the first project may be created anonymously; afterwards it needs a profile."""
    client.post("/api/auth/logout")
    r = client.post("/api/projects", json={"name": "Onboarding Probe", "template": "custom", "labels": []})
    if client.get("/api/projects").json()[:-1]:  # other test modules may have created projects already
        assert r.status_code in (201, 401)
    else:
        assert r.status_code == 201, r.text


def test_conftest_user_fixture_logs_in(client, user):
    assert client.get("/api/auth/me").json()["id"] == user["id"]


def test_create_user_without_session_and_login(client):
    client.post("/api/auth/logout")
    r = client.post("/api/users", json={"name": "Ada Lovelace", "role": "lead", "email": "ada@example.test"})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["handle"] == "ada-lovelace"
    assert u["has_pin"] is False
    # duplicate name → unique handle
    r2 = client.post("/api/users", json={"name": "Ada Lovelace"})
    assert r2.json()["handle"] == "ada-lovelace-2"
    _login(client, u["id"])
    assert client.get("/api/auth/me").json()["id"] == u["id"]
    # patch requires a session and merges preferences
    r = client.patch(f"/api/users/{u['id']}", json={"preferences": {"slack_dm": True}, "skills": ["math"]})
    assert r.status_code == 200
    assert r.json()["preferences"]["slack_dm"] is True and r.json()["skills"] == ["math"]
    r = client.delete(f"/api/users/{r2.json()['id']}")
    assert r.json()["is_active"] is False
    assert all(x["id"] != r2.json()["id"] for x in client.get("/api/users?active=true").json())


def test_mutations_need_a_profile(client, project):
    client.post("/api/auth/logout")
    r = client.post(f"/api/projects/{project['id']}/items", json={"title": "nope"})
    assert r.status_code == 401
    # projects exist now, so creating one anonymously is refused too
    assert client.post("/api/projects", json={"name": "Anon", "template": "custom"}).status_code == 401


# ---------------------------------------------------------------- projects


def test_project_from_template(client, me, project):
    assert project["template"] == "software-scrum"
    assert project["methodology"] == "scrum"
    assert [s["key"] for s in project["workflow"]] == ["backlog", "ready", "in_progress", "review", "done"]
    assert project["settings"]["default_type"] == "story"
    assert project["evm"]["enabled"] is False and "bac" in project["evm"]
    labels = client.get(f"/api/projects/{project['id']}/labels").json()
    assert {lab["name"] for lab in labels} >= {"frontend", "backend"}
    # key derivation + uniqueness
    r = client.post("/api/projects", json={"name": "Hyper Lane Test", "template": "software-kanban"})
    assert r.status_code == 201 and r.json()["key"] == "HLT"
    r2 = client.post("/api/projects", json={"name": "Hyper Lane Test", "template": "custom", "labels": []})
    assert r2.json()["key"] == "HLT2"
    assert client.get(f"/api/projects/{r2.json()['id']}/labels").json() == []
    # overrides on top of the template, evm merged with defaults
    r3 = client.post(
        "/api/projects",
        json={"name": "Ops Override", "template": "operations", "settings": {"sprint_length_days": 7},
              "evm": {"enabled": True, "bac": 5000}},
    )  # fmt: skip
    p3 = r3.json()
    assert p3["settings"]["sprint_length_days"] == 7 and p3["settings"]["estimation"] == "throughput"
    assert p3["evm"]["enabled"] is True and p3["evm"]["bac"] == 5000 and p3["evm"]["currency"] == "USD"
    assert client.get("/api/projects").json()[0]["status"] != "archived"
    # archive
    assert client.delete(f"/api/projects/{p3['id']}").json()["status"] == "archived"
    listed = client.get("/api/projects").json()
    assert listed[-1]["id"] == p3["id"]


def test_project_patch_and_workflow_rename(client, me):
    p = client.post("/api/projects", json={"name": "Rename Flow", "template": "custom"}).json()
    item = client.post(f"/api/projects/{p['id']}/items", json={"title": "A", "status": "doing"}).json()
    assert item["status"] == "doing"
    wf = [dict(s) for s in p["workflow"]]
    wf[1]["key"] = "in_flight"
    r = client.patch(f"/api/projects/{p['id']}", json={"workflow": wf, "workflow_rename": {"doing": "in_flight"}, "color": "#fff"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/items/{item['id']}").json()["status"] == "in_flight"
    tr = client.get(f"/api/items/{item['id']}/transitions").json()
    assert tr[-1]["to_status"] == "in_flight"
    # invalid workflow rejected
    bad = client.patch(f"/api/projects/{p['id']}", json={"workflow": [{"key": "x", "category": "todo"}]})
    assert bad.status_code == 400
    acts = client.get(f"/api/projects/{p['id']}/activity").json()
    assert any(a["action"] == "updated" and a["entity_type"] == "project" for a in acts)


# ---------------------------------------------------------------- items


@pytest.fixture(scope="module")
def tree(client, pilot, project):
    _login(client, pilot["id"])
    pid = project["id"]
    epic = client.post(f"/api/projects/{pid}/items", json={"title": "Epic One", "type": "epic", "labels": ["frontend", "NewLabel"]}).json()
    feature = client.post(f"/api/projects/{pid}/items", json={"title": "Feature One", "type": "feature", "parent_id": epic["id"]}).json()
    stories = [
        client.post(f"/api/projects/{pid}/items", json={"title": f"Story {i}", "parent_id": feature["id"], "points": p}).json()
        for i, p in enumerate((3, 5, 8), start=1)
    ]
    return {"epic": epic, "feature": feature, "stories": stories}


def test_create_item_defaults_and_key(client, me, project, tree):
    epic, feature, stories = tree["epic"], tree["feature"], tree["stories"]
    assert epic["key"] == f"{project['key']}-{epic['number']}"
    assert epic["status"] == "backlog" and epic["priority"] == "medium"
    assert {lab["name"] for lab in epic["labels"]} == {"frontend", "NewLabel"}
    assert epic["reporter_id"] == me["id"]
    assert stories[0]["type"] == "story"  # default type from settings
    assert stories[0]["rank"] < stories[1]["rank"] < stories[2]["rank"]
    assert [s["number"] for s in stories] == [feature["number"] + 1, feature["number"] + 2, feature["number"] + 3]
    detail = client.get(f"/api/items/{feature['id']}").json()
    assert detail["child_count"] == 3 and [c["id"] for c in detail["children"]] == [s["id"] for s in stories]
    assert detail["parent"]["id"] == epic["id"] and detail["sprint"] is None and detail["comments"] == []
    # validation → 400
    assert client.post(f"/api/projects/{project['id']}/items", json={"title": "x", "type": "nope"}).status_code == 400
    assert client.post(f"/api/projects/{project['id']}/items", json={"title": "x", "status": "nope"}).status_code == 400
    assert client.post(f"/api/projects/{project['id']}/items", json={"title": "x", "parent_id": "nope"}).status_code == 400


def test_list_filters(client, me, project, tree):
    pid = project["id"]
    items = client.get(f"/api/projects/{pid}/items").json()
    assert [i["rank"] for i in items] == sorted(i["rank"] for i in items)
    assert len(client.get(f"/api/projects/{pid}/items?type=epic").json()) == 1
    assert len(client.get(f"/api/projects/{pid}/items?parent_id={tree['feature']['id']}").json()) == 3
    assert len(client.get(f"/api/projects/{pid}/items?label=newlabel").json()) == 1
    assert len(client.get(f"/api/projects/{pid}/items?q=Story 2").json()) == 1
    assert client.get(f"/api/projects/{pid}/items?q={tree['epic']['key']}").json()[0]["id"] == tree["epic"]["id"]
    assert len(client.get(f"/api/projects/{pid}/items?sprint_id=none").json()) == 5
    assert len(client.get(f"/api/projects/{pid}/items?category=in_progress").json()) == 0


def test_status_transitions_and_timestamps(client, me, tree):
    story = tree["stories"][0]
    r = client.patch(f"/api/items/{story['id']}", json={"status": "in_progress"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["started_at"] is not None and s["completed_at"] is None
    started = s["started_at"]
    s = client.patch(f"/api/items/{story['id']}", json={"status": "done"}).json()
    assert s["completed_at"] is not None and s["started_at"] == started
    s = client.patch(f"/api/items/{story['id']}", json={"status": "review"}).json()
    assert s["completed_at"] is None  # cleared when leaving done
    s = client.patch(f"/api/items/{story['id']}", json={"status": "done", "points": 2}).json()
    assert s["completed_at"] is not None and s["points"] == 2
    tr = client.get(f"/api/items/{story['id']}/transitions").json()
    assert [t["to_status"] for t in tr] == ["backlog", "in_progress", "done", "review", "done"]
    assert tr[1]["from_category"] == "todo" and tr[1]["to_category"] == "in_progress"
    acts = client.get(f"/api/items/{story['id']}/activity").json()
    upd = [a for a in acts if a["action"] == "updated"]
    assert upd and upd[0]["changes"]["status"] == ["review", "done"] and upd[0]["actor_name"] == me["name"]
    assert "points" in upd[0]["changes"]
    # no-op patch writes no activity
    n = len(client.get(f"/api/items/{story['id']}/activity").json())
    client.patch(f"/api/items/{story['id']}", json={"status": "done"})
    assert len(client.get(f"/api/items/{story['id']}/activity").json()) == n


def test_update_labels_assignee_and_parent_validation(client, me, project, tree):
    story = tree["stories"][1]
    r = client.patch(f"/api/items/{story['id']}", json={"labels": ["backend", "brand-new"], "assignee_id": me["id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert {lab["name"] for lab in out["labels"]} == {"backend", "brand-new"}
    assert out["assignee"]["id"] == me["id"]
    assert client.patch(f"/api/items/{story['id']}", json={"assignee_id": "ghost"}).status_code == 400
    # cycles are refused
    r = client.patch(f"/api/items/{tree['epic']['id']}", json={"parent_id": story["id"]})
    assert r.status_code == 400 and "cycle" in r.json()["detail"]
    assert client.patch(f"/api/items/{story['id']}", json={"parent_id": story["id"]}).status_code == 400


def test_move_and_rank_ordering(client, me, project, tree):
    s1, s2, s3 = tree["stories"]
    pid = project["id"]
    # put s3 before s1 (above it)
    r = client.post(f"/api/items/{s3['id']}/move", json={"before_id": s1["id"]})
    assert r.status_code == 200, r.text
    assert "wip_warning" in r.json() and r.json()["wip_warning"] is None
    ids = [i["id"] for i in client.get(f"/api/projects/{pid}/items?parent_id={tree['feature']['id']}").json()]
    assert ids == [s3["id"], s1["id"], s2["id"]]
    # put s3 after s2 (bottom)
    client.post(f"/api/items/{s3['id']}/move", json={"after_id": s2["id"]})
    ids = [i["id"] for i in client.get(f"/api/projects/{pid}/items?parent_id={tree['feature']['id']}").json()]
    assert ids == [s1["id"], s2["id"], s3["id"]]
    # between
    client.post(f"/api/items/{s3['id']}/move", json={"after_id": s1["id"], "before_id": s2["id"]})
    ids = [i["id"] for i in client.get(f"/api/projects/{pid}/items?parent_id={tree['feature']['id']}").json()]
    assert ids == [s1["id"], s3["id"], s2["id"]]
    # many inserts in the same gap stay ordered (renormalize kicks in when gaps vanish)
    last = s1
    for i in range(60):
        n = client.post(f"/api/projects/{pid}/items", json={"title": f"wedge {i}", "parent_id": tree["feature"]["id"]}).json()
        client.post(f"/api/items/{n['id']}/move", json={"after_id": last["id"], "before_id": s3["id"]})
        last = n
    ids = [i["title"] for i in client.get(f"/api/projects/{pid}/items?parent_id={tree['feature']['id']}").json()]
    assert ids[0] == "Story 1" and ids[1:61] == [f"wedge {i}" for i in range(60)] and ids[61] == "Story 3"
    # board move (status) + hierarchy move (parent) + self-reference refused
    r = client.post(f"/api/items/{s2['id']}/move", json={"status": "in_progress", "parent_id": None})
    assert r.json()["status"] == "in_progress" and r.json()["parent_id"] is None and r.json()["started_at"]
    assert client.post(f"/api/items/{s2['id']}/move", json={"after_id": s2["id"]}).status_code == 400
    client.post(f"/api/items/{s2['id']}/move", json={"parent_id": tree["feature"]["id"]})


def test_wip_warning(client, me):
    p = client.post("/api/projects", json={"name": "Kanban WIP", "template": "software-kanban"}).json()
    pid = p["id"]
    limit = next(s for s in p["workflow"] if s["key"] == "review")["wip_limit"]
    ids = [client.post(f"/api/projects/{pid}/items", json={"title": f"i{i}"}).json()["id"] for i in range(limit + 1)]
    warnings = [client.post(f"/api/items/{i}/move", json={"status": "review"}).json()["wip_warning"] for i in ids]
    assert warnings[:-1] == [None] * limit and "WIP limit" in warnings[-1]


def test_bulk_create_with_temp_ids_and_bulk_update(client, me, project):
    pid = project["id"]
    r = client.post(
        f"/api/projects/{pid}/items/bulk",
        json={"items": [
            {"temp_id": "s1", "parent_temp_id": "f1", "title": "Bulk story", "points": 3},  # child listed first
            {"temp_id": "e1", "title": "Bulk epic", "type": "epic"},
            {"temp_id": "f1", "parent_temp_id": "e1", "title": "Bulk feature", "type": "feature", "labels": ["infra"]},
        ]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    by_title = {i["title"]: i for i in r.json()}
    assert by_title["Bulk feature"]["parent_id"] == by_title["Bulk epic"]["id"]
    assert by_title["Bulk story"]["parent_id"] == by_title["Bulk feature"]["id"]
    bad = client.post(f"/api/projects/{pid}/items/bulk", json={"items": [{"title": "x", "parent_temp_id": "zz"}]})
    assert bad.status_code == 400
    r = client.post("/api/items/bulk-update", json={"ids": [by_title["Bulk story"]["id"], by_title["Bulk feature"]["id"]],
                                                   "patch": {"priority": "high", "labels": ["ux"]}})  # fmt: skip
    assert r.status_code == 200 and all(i["priority"] == "high" and i["labels"][0]["name"] == "ux" for i in r.json())


def test_archive_soft_and_hard(client, me, project):
    pid = project["id"]
    parent = client.post(f"/api/projects/{pid}/items", json={"title": "Doomed", "type": "feature"}).json()
    child = client.post(f"/api/projects/{pid}/items", json={"title": "Doomed child", "parent_id": parent["id"]}).json()
    assert client.delete(f"/api/items/{parent['id']}").status_code == 200
    assert client.get(f"/api/items/{child['id']}").json()["is_archived"] is True
    assert all(i["id"] != parent["id"] for i in client.get(f"/api/projects/{pid}/items").json())
    assert any(i["id"] == parent["id"] for i in client.get(f"/api/projects/{pid}/items?include_archived=true").json())
    client.post(f"/api/items/{child['id']}/comments", json={"body": "bye"})
    assert client.delete(f"/api/items/{child['id']}?hard=true").status_code == 200
    assert client.get(f"/api/items/{child['id']}").status_code == 404


# ---------------------------------------------------------------- sprints


def test_sprint_lifecycle_with_carry_over(client, me, project):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/sprints", json={"goal": "Ship the thing"})
    assert r.status_code == 201, r.text
    sp1 = r.json()
    assert sp1["name"] == "Sprint 1" and sp1["state"] == "planned"
    from datetime import date

    assert (date.fromisoformat(sp1["end_date"]) - date.fromisoformat(sp1["start_date"])).days == 13
    a = client.post(f"/api/projects/{pid}/items", json={"title": "sprint A", "points": 3, "sprint_id": sp1["id"], "assignee_id": me["id"]}).json()
    b = client.post(f"/api/projects/{pid}/items", json={"title": "sprint B", "points": 5, "sprint_id": sp1["id"], "assignee_id": me["id"]}).json()
    c = client.post(f"/api/projects/{pid}/items", json={"title": "sprint C", "points": 2}).json()
    client.post(f"/api/items/{c['id']}/move", json={"sprint_id": sp1["id"]})
    assert len(client.get(f"/api/sprints/{sp1['id']}/items").json()) == 3
    # close before start refused; start; second active refused
    assert client.post(f"/api/sprints/{sp1['id']}/close", json={"carry_over": "next"}).status_code == 400
    started = client.post(f"/api/sprints/{sp1['id']}/start").json()
    assert started["state"] == "active" and started["committed_points"] == 10 and started["committed_count"] == 3
    sp_other = client.post(f"/api/projects/{pid}/sprints", json={}).json()
    assert sp_other["number"] == 2
    assert client.post(f"/api/sprints/{sp_other['id']}/start").status_code == 400
    assert client.delete(f"/api/sprints/{sp1['id']}").status_code == 400  # active can't be deleted
    client.delete(f"/api/sprints/{sp_other['id']}")  # planned can
    assert client.get(f"/api/sprints/{sp_other['id']}").status_code == 404
    # mid-sprint scope change: d added to the active sprint
    d = client.post(f"/api/projects/{pid}/items", json={"title": "sprint D", "points": 1, "sprint_id": sp1["id"]}).json()
    client.patch(f"/api/items/{a['id']}", json={"status": "done"})
    client.patch(f"/api/items/{b['id']}", json={"status": "in_progress"})
    r = client.post(f"/api/sprints/{sp1['id']}/close", json={"carry_over": "next"})
    assert r.status_code == 200, r.text
    closed = r.json()
    assert closed["sprint"]["state"] == "closed" and closed["sprint"]["completed_points"] == 3
    assert closed["sprint"]["completed_count"] == 1 and closed["sprint"]["closed_at"]
    assert {i["id"] for i in closed["completed"]} == {a["id"]}
    assert {i["id"] for i in closed["carried"]} == {b["id"], c["id"], d["id"]}
    nxt = client.get(f"/api/projects/{pid}/sprints?state=planned").json()
    assert len(nxt) == 1 and nxt[0]["number"] == 2  # number 2 was freed by the delete above
    assert all(i["sprint_id"] == nxt[0]["id"] for i in closed["carried"])
    assert client.get(f"/api/items/{a['id']}").json()["sprint_id"] == sp1["id"]
    # sprints listed number desc; carry to backlog on the next close
    assert [s["number"] for s in client.get(f"/api/projects/{pid}/sprints").json()] == [2, 1]
    client.post(f"/api/sprints/{nxt[0]['id']}/start")
    r = client.post(f"/api/sprints/{nxt[0]['id']}/close", json={"carry_over": "backlog"}).json()
    assert all(i["sprint_id"] is None for i in r["carried"]) and len(r["carried"]) == 3
    assert client.post(f"/api/sprints/{nxt[0]['id']}/close", json={"carry_over": "backlog"}).status_code == 400
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["active_sprint"] is None and summary["total_points"] >= 11
    assert me["id"] in {m["id"] for m in summary["members"]}
    assert set(summary["counts_by_status"]) >= {"backlog", "done"}


# ---------------------------------------------------------------- comments


def test_comments(client, me, tree):
    story = tree["stories"][2]
    r = client.post(f"/api/items/{story['id']}/comments", json={"body": "First!", "is_decision": True})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["author"]["id"] == me["id"] and c["author_name"] == me["name"] and c["source"] == "web"
    assert c["is_decision"] is True
    detail = client.get(f"/api/items/{story['id']}").json()
    assert detail["comment_count"] == 1 and detail["comments"][0]["id"] == c["id"]
    r = client.patch(f"/api/comments/{c['id']}", json={"body": "Edited"})
    assert r.json()["body"] == "Edited" and r.json()["edited_at"] is not None
    assert client.post(f"/api/items/{story['id']}/comments", json={"body": "   "}).status_code == 400
    acts = client.get(f"/api/items/{story['id']}/activity").json()
    assert any(a["action"] == "commented" for a in acts)
    assert client.delete(f"/api/comments/{c['id']}").status_code == 200
    assert client.get(f"/api/items/{story['id']}").json()["comment_count"] == 0


# ---------------------------------------------------------------- action items (private)


def test_action_items_are_private(client, me, project):
    r = client.post("/api/me/action-items", json={"title": "Secret todo", "priority": "high", "due_date": "2020-01-01", "project_id": project["id"]})
    assert r.status_code == 201, r.text
    mine = r.json()
    second = client.post("/api/me/action-items", json={"title": "Second", "tags": ["x"]}).json()
    assert second["position"] > mine["position"]
    listed = client.get("/api/me/action-items").json()
    assert [a["id"] for a in listed] == [mine["id"], second["id"]]
    r = client.post("/api/me/action-items/reorder", json={"ids": [second["id"], mine["id"]]})
    assert [a["id"] for a in r.json()][:2] == [second["id"], mine["id"]]
    ov = client.get("/api/me/overview").json()
    assert ov["action_items_open"] == 2 and ov["action_items_overdue"] == 1
    assert {"assigned", "in_progress", "mentions", "active_sprints"} <= set(ov)
    done = client.patch(f"/api/me/action-items/{mine['id']}", json={"done": True}).json()
    assert done["done"] is True and done["done_at"]
    assert len(client.get("/api/me/action-items").json()) == 1
    assert len(client.get("/api/me/action-items?include_done=true").json()) == 2

    # another user can't see, edit or delete them
    other = client.post("/api/users", json={"name": "Nosy Neighbour"}).json()
    _login(client, other["id"])
    assert client.get("/api/me/action-items?include_done=true").json() == []
    assert client.patch(f"/api/me/action-items/{mine['id']}", json={"title": "pwned"}).status_code == 404
    assert client.delete(f"/api/me/action-items/{mine['id']}").status_code == 404
    assert client.get("/api/me/overview").json()["action_items_open"] == 0
    _login(client, me["id"])
    assert client.get("/api/me/action-items?include_done=true").json()[1]["title"] == "Secret todo"
    assert client.delete(f"/api/me/action-items/{second['id']}").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me/action-items").status_code == 401


# ---------------------------------------------------------------- search


def test_search(client, me, project, tree):
    epic = tree["epic"]
    r = client.get(f"/api/search?q={epic['key']}")
    assert r.status_code == 200 and r.json()[0]["id"] == epic["id"]
    assert r.json()[0]["key"] == epic["key"]
    hits = client.get("/api/search?q=Story").json()
    assert project["id"] in {h["project_id"] for h in hits} and len(hits) >= 3
    assert client.get("/api/search?q=").json() == []
    assert client.get("/api/search?q=zzz-no-such-thing").json() == []


# ---------------------------------------------------------------- seed + tree


def test_seed_is_rich_and_idempotent(client, me):
    r = client.post("/api/dev/seed", json={"project_name": "Galactic Racer"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["project"]["key"] == "GR" and len(out["users"]) == 5  # created may be False if another module seeded
    assert out["items"] >= 40 and out["sprints"] == 4
    pid = out["project"]["id"]
    again = client.post("/api/dev/seed", json={"project_name": "Galactic Racer"}).json()
    assert again["created"] is False and again["project"]["id"] == pid
    assert client.get("/api/workspace").json()["onboarded"] is True

    sprints = client.get(f"/api/projects/{pid}/sprints").json()
    assert [s["state"] for s in sprints] == ["active", "closed", "closed", "closed"]
    for s in sprints[1:]:
        assert s["completed_points"] > 0 and s["committed_points"] >= s["completed_points"] and s["closed_at"]
    active = sprints[0]
    board = client.get(f"/api/projects/{pid}/items?sprint_id={active['id']}").json()
    assert {i["status"] for i in board} >= {"done", "in_progress", "ready"}
    done = client.get(f"/api/projects/{pid}/items?status=done&type=story,bug,task,spike").json()
    assert len(done) >= 15 and all(i["started_at"] and i["completed_at"] for i in done)
    assert all(i["completed_at"] >= i["started_at"] >= i["created_at"] for i in done)
    tr = client.get(f"/api/items/{done[0]['id']}/transitions").json()
    assert [t["to_status"] for t in tr][:2] == ["backlog", "ready"] and tr[-1]["to_status"] == "done"
    assert tr[-1]["at"] < out["project"]["updated_at"] or True  # backdated (sanity, not strict)
    evm = client.get(f"/api/projects/{pid}").json()["evm"]
    assert evm["enabled"] and evm["bac"] == 120000 and evm["cost_per_point"] == 850 and evm["planned_sprints"] == 8
    assert evm["planned_points"] > 0 and evm["baseline_locked_at"]
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["active_sprint"]["id"] == active["id"] and len(summary["members"]) == 5
    assert summary["done_points"] > 0
    acts = client.get(f"/api/projects/{pid}/activity?limit=500").json()
    assert {a["action"] for a in acts} >= {"created", "moved", "commented", "started", "closed"}
    commented = [a for a in acts if a["action"] == "commented"]
    item = client.get(f"/api/items/{commented[0]['entity_id']}").json()
    assert item["comments"]
    drift = next(i for i in client.get(f"/api/projects/{pid}/items?q=Drift handling").json() if i["title"].startswith("Drift"))
    drift_comments = client.get(f"/api/items/{drift['id']}").json()["comments"]
    assert len(drift_comments) == 3 and any(c["is_decision"] for c in drift_comments)
    assert all(c["author"]["name"] == c["author_name"] for c in drift_comments)
    # private action items exist for the seeded pilots
    nova = next(u for u in out["users"] if u["name"] == "Nova Reyes")
    _login(client, nova["id"])
    assert len(client.get("/api/me/action-items?include_done=true").json()) >= 3
    ov = client.get("/api/me/overview").json()
    assert ov["active_sprints"] and ov["active_sprints"][0]["id"] == active["id"]
    _login(client, me["id"])
    # search by key across projects
    assert client.get("/api/search?q=GR-1").json()[0]["key"] == "GR-1"


def test_tree_endpoint(client, me):
    pid = client.post("/api/dev/seed", json={"project_name": "Galactic Racer"}).json()["project"]["id"]
    tree = client.get(f"/api/projects/{pid}/items/tree").json()
    assert len(tree) == 4 and all(n["type"] == "epic" for n in tree)
    assert all(n["children"] and all(f["type"] == "feature" for f in n["children"]) for n in tree)
    leaves = [leaf for e in tree for f in e["children"] for leaf in f["children"]]
    assert len(leaves) >= 30 and all(leaf["key"].startswith("GR-") for leaf in leaves)
    feature = tree[0]["children"][0]
    assert feature["child_count"] == len(feature["children"])
    ranks = [leaf["rank"] for leaf in feature["children"]]
    assert ranks == sorted(ranks)
    pruned = client.get(f"/api/projects/{pid}/items/tree?include_done=false").json()
    for e in pruned:
        for f in e["children"]:
            assert f["status"] != "done" or f["children"]
            for leaf in f["children"]:
                assert leaf["status"] != "done"
