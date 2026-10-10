"""backend-analytics: metrics, forecast, EVM, capacity, retro.

All fixture data is written straight through the ORM so these tests do not depend on
backend-core's services or routers.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from hyperlane.db import session_scope, utcnow
from hyperlane.models import (
    ActionItem,
    CapacityEntry,
    CapacityProfile,
    Project,
    Sprint,
    SprintCommitment,
    StatusTransition,
    User,
    WorkItem,
)
from hyperlane.services import capacity, evm, forecast, metrics, retro
from hyperlane.services.templates import default_evm, get_template

TODAY = utcnow().date()


def _dt(day_offset: int, hour: int = 12) -> datetime:
    return datetime.combine(TODAY + timedelta(days=day_offset), time(hour=hour))


def _d(day_offset: int) -> date:
    return TODAY + timedelta(days=day_offset)


class Data:
    """Ids of everything the fixture created."""

    project_id: str
    evm_project_id: str
    users: dict[str, str]
    sprints: dict[int, str]
    backlog: dict[str, str]
    evm_done_ids: list[str]


def _add_item(db, project, number, title, *, status, points, created, assignee=None, sprint_id=None, **kw):
    item = WorkItem(
        project_id=project.id,
        number=number,
        type=kw.pop("type", "story"),
        title=title,
        status=status,
        points=points,
        created_at=created,
        updated_at=created,
        assignee_id=assignee,
        sprint_id=sprint_id,
        rank=float(number),
        **kw,
    )
    db.add(item)
    db.flush()
    return item


def _transition(db, item, from_status, to_status, cats, at):
    db.add(
        StatusTransition(
            work_item_id=item.id,
            project_id=item.project_id,
            from_status=from_status,
            to_status=to_status,
            from_category=cats.get(from_status) if from_status else None,
            to_category=cats[to_status],
            at=at,
        )
    )


@pytest.fixture(scope="module")
def data(client) -> Data:
    tpl = get_template("software-scrum")
    cats = {s["key"]: s["category"] for s in tpl["workflow"]}
    suffix = uuid.uuid4().hex[:4]
    d = Data()
    with session_scope() as db:
        users = {}
        for name in ("Alex", "Blair", "Casey"):
            u = User(name=name, handle=f"{name.lower()}-{suffix}", hours_per_week=40, focus_factor=0.7)
            db.add(u)
            db.flush()
            users[name] = u.id
        d.users = users
        alex, blair, casey = users["Alex"], users["Blair"], users["Casey"]

        workflow = tpl["workflow"]
        workflow[3]["wip_limit"] = 1  # review limit so we can breach it
        project = Project(
            key=f"AN{suffix[:2].upper()}",
            name="Analytics Project",
            template="software-scrum",
            item_types=tpl["item_types"],
            workflow=workflow,
            settings=tpl["settings"],
            evm=default_evm(),
            lead_id=alex,
        )
        db.add(project)
        db.flush()
        d.project_id = project.id

        # ---- three closed sprints + one active + one planned ----
        starts = {1: -56, 2: -42, 3: -28, 4: -7, 5: 7}
        sprints = {}
        for n, s in starts.items():
            sp = Sprint(
                project_id=project.id,
                number=n,
                name=f"Sprint {n}",
                start_date=_d(s),
                end_date=_d(s + 13),
                state="closed" if n <= 3 else ("active" if n == 4 else "planned"),
                closed_at=_dt(s + 13, 18) if n <= 3 else None,
            )
            db.add(sp)
            db.flush()
            sprints[n] = sp
        d.sprints = {n: sp.id for n, sp in sprints.items()}

        number = 1
        # (points, done_offset_from_sprint_start or None, cycle_days, assignee)
        plan = {
            1: [(3, 3, 2, alex), (3, 5, 3, blair), (3, 10, 4, casey), (3, None, None, alex)],
            2: [(5, 3, 2, alex), (3, 5, 2, blair), (2, 9, 3, casey), (3, 11, 5, alex)],
            3: [(5, 3, 3, alex), (5, 8, 4, blair), (2, 12, 2, casey), (3, None, None, blair), (2, None, None, casey)],
        }
        per_user_done = {1: {}, 2: {}, 3: {}}
        per_user_planned = {1: {}, 2: {}, 3: {}}
        for n, rows in plan.items():
            sp = sprints[n]
            s = starts[n]
            committed = completed = 0.0
            for pts, done_off, cycle, who in rows:
                created = _dt(s - 3, 9)
                status = "done" if done_off is not None else "ready"
                item = _add_item(
                    db, project, number, f"S{n} item {number}", status=status, points=pts, created=created,
                    assignee=who, sprint_id=sp.id if done_off is None else None,
                )
                number += 1
                committed += pts
                per_user_planned[n][who] = per_user_planned[n].get(who, 0) + pts
                _transition(db, item, "backlog", "ready", cats, created + timedelta(hours=1))
                db.add(SprintCommitment(sprint_id=sp.id, work_item_id=item.id, points=pts, added_at=_dt(s, 9)))
                if done_off is not None:
                    done_at = _dt(s + done_off, 15)
                    started = done_at - timedelta(days=cycle)
                    _transition(db, item, "ready", "in_progress", cats, started)
                    _transition(db, item, "in_progress", "done", cats, done_at)
                    item.started_at = started
                    item.completed_at = done_at
                    item.sprint_id = sp.id
                    completed += pts
                    per_user_done[n][who] = per_user_done[n].get(who, 0) + pts
                else:
                    # carried over: left the sprint at close
                    item.sprint_id = None
            sp.committed_points = committed
            sp.committed_count = len(rows)
            sp.completed_points = completed
            sp.completed_count = sum(1 for r in rows if r[1] is not None)
            for who in (alex, blair, casey):
                db.add(
                    CapacityEntry(
                        sprint_id=sp.id, user_id=who, days_off=0, available_hours=56.0,
                        planned_points=per_user_planned[n].get(who, 0), planned_count=1,
                        completed_points=per_user_done[n].get(who, 0),
                        completed_count=1 if per_user_done[n].get(who) else 0,
                    )
                )

        # ---- active sprint 4: 3 items (one done, one in review, one in progress) ----
        sp4 = sprints[4]
        a1 = _add_item(db, project, number, "Active done", status="done", points=5, created=_dt(-10), assignee=alex, sprint_id=sp4.id)
        number += 1
        a1.started_at, a1.completed_at = _dt(-6), _dt(-3)
        _transition(db, a1, "ready", "in_progress", cats, _dt(-6))
        _transition(db, a1, "in_progress", "done", cats, _dt(-3))
        a2 = _add_item(db, project, number, "Active review", status="review", points=3, created=_dt(-10), assignee=blair, sprint_id=sp4.id)
        number += 1
        _transition(db, a2, "ready", "in_progress", cats, _dt(-5))
        _transition(db, a2, "in_progress", "review", cats, _dt(-2))
        a3 = _add_item(db, project, number, "Active review 2", status="review", points=2, created=_dt(-10), assignee=casey, sprint_id=sp4.id)
        number += 1
        _transition(db, a3, "ready", "in_progress", cats, _dt(-4))
        _transition(db, a3, "in_progress", "review", cats, _dt(-1))
        for it in (a1, a2, a3):
            db.add(SprintCommitment(sprint_id=sp4.id, work_item_id=it.id, points=it.points, added_at=_dt(-7, 9)))
        a4 = _add_item(db, project, number, "Added mid sprint", status="ready", points=2, created=_dt(-3), sprint_id=sp4.id)
        number += 1
        db.add(SprintCommitment(sprint_id=sp4.id, work_item_id=a4.id, points=2, added_at=_dt(-3, 10), added_mid_sprint=True))

        # ---- backlog candidates ----
        backlog = {}
        epic = _add_item(db, project, number, "Big epic", status="backlog", points=None, created=_dt(-40), type="epic")
        number += 1
        backlog["epic"] = epic.id
        feature = _add_item(db, project, number, "Feature with children", status="backlog", points=None, created=_dt(-40), type="feature", parent_id=epic.id)
        number += 1
        backlog["feature"] = feature.id
        specs = [
            ("crit", "critical", 8, 90, None, False),
            ("high", "high", 5, 70, alex, False),
            ("med1", "medium", 5, 40, blair, False),
            ("med2", "medium", 3, None, None, False),
            ("low", "low", 8, 10, casey, False),
            ("blocked", "high", 3, 80, None, True),
            ("old", "medium", 2, None, None, False),
            ("big", "medium", 13, 50, None, False),
            ("overdue", "medium", 1, None, alex, False),
        ]
        for key, prio, pts, bv, who, blocked in specs:
            it = _add_item(
                db, project, number, f"Backlog {key}", status="ready", points=pts, created=_dt(-30 if key == "old" else -5),
                assignee=who, priority=prio, business_value=bv, blocked=blocked, parent_id=feature.id,
                due_date=_d(-2) if key == "overdue" else None,
            )
            number += 1
            backlog[key] = it.id
        d.backlog = backlog

        # ---- EVM project (hand-computed example) ----
        evm_project = Project(
            key=f"EV{suffix[:2].upper()}",
            name="EVM Example",
            template="software-scrum",
            item_types=tpl["item_types"],
            workflow=get_template("software-scrum")["workflow"],
            settings=tpl["settings"],
            evm={**default_evm(), "enabled": True, "bac": 100000.0, "planned_points": 100.0, "planned_sprints": 5,
                 "start_date": _d(-60).isoformat(), "end_date": _d(40).isoformat()},
        )
        db.add(evm_project)
        db.flush()
        d.evm_project_id = evm_project.id
        for n in (1, 2):
            db.add(Sprint(project_id=evm_project.id, number=n, name=f"E{n}", start_date=_d(-60 + (n - 1) * 14),
                          end_date=_d(-47 + (n - 1) * 14), state="closed", closed_at=_dt(-47 + (n - 1) * 14)))
        d.evm_done_ids = []
        for i in range(3):
            it = _add_item(db, evm_project, i + 1, f"E done {i}", status="done", points=10, created=_dt(-50),
                           actual_cost=35000.0 if i == 0 else 0.0)
            it.completed_at = _dt(-40 + i * 5)
            d.evm_done_ids.append(it.id)
        for i in range(7):
            _add_item(db, evm_project, i + 4, f"E todo {i}", status="ready", points=10, created=_dt(-50))
    return d


@pytest.fixture(scope="module")
def auth(client, data):
    client.post("/api/auth/login", json={"user_id": data.users["Alex"]})
    return client


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def test_velocity_and_overview(auth, data):
    r = auth.get(f"/api/projects/{data.project_id}/metrics/overview")
    assert r.status_code == 200, r.text
    o = r.json()
    assert [v["sprint"] for v in o["velocity"]] == ["Sprint 1", "Sprint 2", "Sprint 3"]
    assert [v["committed"] for v in o["velocity"]] == [12, 13, 17]
    assert [v["completed"] for v in o["velocity"]] == [9, 13, 12]
    assert o["avg_velocity"] == pytest.approx((9 + 13 + 12) / 3, abs=0.01)
    assert isinstance(o["velocity_trend"], float)
    assert o["wip"] == 2  # two items in review (in_progress category)
    assert o["wip_limit_breaches"] == [{"status": "review", "count": 2, "limit": 1}]
    assert o["blocked"] == 1
    assert o["overdue"] == 1
    active = o["active_sprint"]
    assert active and active["sprint"]["id"] == data.sprints[4]
    assert active["days_left"] == 6
    assert 0 <= active["pct_time"] <= 100
    assert active["pct_scope_done"] == pytest.approx(5 / 12 * 100, abs=0.1)
    assert 0 <= o["health"]["score"] <= 100
    names = {s["name"]: s for s in o["health"]["signals"]}
    assert names["wip"]["status"] == "bad" and "over limit 1 in In Review" in names["wip"]["detail"]
    assert names["blocked"]["detail"] == "1 blocked item"
    assert o["flow_efficiency"] is not None and 0 < o["flow_efficiency"] <= 1
    assert set(o) == {
        "project_id", "as_of", "velocity", "avg_velocity", "velocity_trend", "throughput_per_week",
        "avg_cycle_time_days", "p85_cycle_time_days", "wip", "wip_limit_breaches", "flow_efficiency",
        "blocked", "overdue", "active_sprint", "health",
    }

    v = auth.get(f"/api/projects/{data.project_id}/metrics/velocity?last=2").json()
    assert [x["sprint"] for x in v] == ["Sprint 2", "Sprint 3"]


def test_throughput_per_week_counts_recent_done(auth, data):
    # done in the last 28 days: the three Sprint 3 items (-25, -20, -16) and the active-sprint item (-3)
    o = auth.get(f"/api/projects/{data.project_id}/metrics/overview").json()
    assert o["throughput_per_week"] == pytest.approx(4 / 4)


def test_cycle_time(auth, data):
    r = auth.get(f"/api/projects/{data.project_id}/metrics/cycle-time?days=90").json()
    cycles = sorted(p["cycle_days"] for p in r["points"])
    # 10 closed-sprint done items + 1 active done (3 days)
    assert cycles == sorted([2, 3, 4, 2, 2, 3, 5, 3, 4, 2, 3])
    assert r["avg"] == pytest.approx(sum(cycles) / len(cycles), abs=0.01)
    assert r["p50"] == 3 and r["p85"] <= r["p95"] <= 5
    assert r["by_type"]["story"] == r["avg"]
    p = r["points"][0]
    assert set(p) == {"item_id", "key", "title", "type", "completed_at", "cycle_days", "lead_days"}
    assert p["lead_days"] >= p["cycle_days"]


def test_throughput_weeks(auth, data):
    r = auth.get(f"/api/projects/{data.project_id}/metrics/throughput?weeks=12").json()
    assert len(r["weeks"]) == 12
    assert date.fromisoformat(r["weeks"][0]["week_start"]).weekday() == 0
    assert sum(w["count"] for w in r["weeks"]) == 11
    assert sum(w["points"] for w in r["weeks"]) == 9 + 13 + 12 + 5
    assert r["avg_count"] == pytest.approx(11 / 12, abs=0.01)


def test_cfd(auth, data):
    r = auth.get(f"/api/projects/{data.project_id}/metrics/cfd?days=60").json()
    assert len(r) == 60
    states = ["backlog", "ready", "in_progress", "review", "done"]
    assert all(set(row) == {"date", *states} for row in r)
    last = r[-1]
    with session_scope() as db:
        items = db.query(WorkItem).filter(WorkItem.project_id == data.project_id, WorkItem.is_archived.is_(False)).all()
        expected = {s: sum(1 for i in items if i.status == s) for s in states}
    assert {s: last[s] for s in states} == expected
    # earlier in time nothing was done yet; counts only grow as items are created
    assert r[0]["done"] <= last["done"]
    assert sum(r[0][s] for s in states) <= sum(last[s] for s in states)


def test_burndown_and_burnup(auth, data):
    bd = auth.get(f"/api/sprints/{data.sprints[4]}/burndown").json()
    assert len(bd) == 14
    ideal = [p["ideal"] for p in bd]
    assert ideal == sorted(ideal, reverse=True) and ideal[0] == 10 and ideal[-1] == 0
    today_point = next(p for p in bd if p["date"] == TODAY.isoformat())
    assert today_point["scope"] == 12 and today_point["done"] == 5 and today_point["remaining"] == 7
    assert bd[0]["scope"] == 10  # mid-sprint addition only appears from day 4
    future = [p for p in bd if date.fromisoformat(p["date"]) > TODAY]
    assert len(future) == 6 and all(p["remaining"] is None for p in future)
    bu = auth.get(f"/api/sprints/{data.sprints[4]}/burnup").json()
    assert [p["date"] for p in bu] == [p["date"] for p in bd]


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------


def test_forecast_how_many_and_when(auth, data):
    r = auth.get(f"/api/projects/{data.project_id}/forecast?mode=how_many&weeks=2&sims=2000").json()
    assert r["mode"] == "how_many" and r["simulations"] == 2000 and r["history_weeks"] == 12
    assert r["warning"] is None
    hm = r["how_many"]
    assert hm["weeks"] == 2
    assert hm["p95"] <= hm["p85"] <= hm["p70"] <= hm["p50"]  # confidence convention
    assert sum(h["count"] for h in hm["histogram"]) == 2000
    again = auth.get(f"/api/projects/{data.project_id}/forecast?mode=how_many&weeks=2&sims=2000").json()
    assert again["how_many"] == hm  # deterministic (seeded from project id)

    w = auth.get(f"/api/projects/{data.project_id}/forecast?mode=when&items=20&sims=2000").json()["when"]
    assert w["items"] == 20
    assert w["p50_date"] <= w["p70_date"] <= w["p85_date"] <= w["p95_date"]
    assert date.fromisoformat(w["p50_date"]) > TODAY


def test_forecast_warns_without_history(auth, data):
    with session_scope() as db:
        project = db.get(Project, data.evm_project_id)
        r = forecast.monte_carlo(db, project, mode="how_many", weeks=2, sims=200, seed=1)
    assert r["warning"] == forecast.NOT_ENOUGH  # only 3 weeks with throughput
    assert r["samples"] and r["samples"][0] > 0  # leading empty weeks trimmed
    # the heuristic summary is used when no agent is importable
    with session_scope() as db:
        sp = db.get(Sprint, data.sprints[2])
        text = retro._heuristic_summary(retro.get_or_create(db, sp), retro.stats(db, sp))
    assert "13 of 13" in text and "strong sprint" in text


# ---------------------------------------------------------------------------
# EVM
# ---------------------------------------------------------------------------


def test_evm_hand_computed(auth, data):
    r = auth.get(f"/api/projects/{data.evm_project_id}/evm")
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["bac"] == 100000
    assert e["pv"] == 40000  # 2 of 5 planned sprints closed
    assert e["ev"] == 30000  # 30 of 100 planned points done
    assert e["ac"] == 35000
    assert e["spi"] == pytest.approx(0.75)
    assert e["cpi"] == pytest.approx(0.857, abs=0.001)
    assert e["eac"] == pytest.approx(116667, abs=1)
    assert e["etc"] == pytest.approx(81667, abs=1)
    assert e["vac"] == pytest.approx(-16667, abs=1)
    assert e["tcpi"] == pytest.approx(70000 / 65000, abs=0.001)
    assert e["sv"] == -10000 and e["cv"] == -5000
    assert e["pct_complete"] == 30 and e["pct_planned"] == 40 and e["pct_spent"] == 35
    assert e["status"] == "off_track"
    assert e["forecast_end_date"] == (TODAY + timedelta(days=54)).isoformat()  # 40 days left / 0.75
    assert "closed sprints" in e["narrative"] and "SPI 0.75" in e["narrative"]
    assert e["series"][0]["date"] == (TODAY - timedelta(days=60)).isoformat()
    assert e["series"][-1] == {"date": TODAY.isoformat(), "pv": 40000, "ev": 30000, "ac": 35000, "sprint_id": None}
    evs = [p["ev"] for p in e["series"]]
    assert evs == sorted(evs) and evs[0] == 0
    assert set(e) == {
        "config", "as_of", "bac", "pv", "ev", "ac", "sv", "cv", "spi", "cpi", "eac", "etc", "vac", "tcpi",
        "pct_complete", "pct_planned", "pct_spent", "forecast_end_date", "series", "status", "narrative",
    }


def test_evm_config_baseline_snapshot(auth, data):
    pid = data.project_id
    e = auth.get(f"/api/projects/{pid}/evm").json()
    assert e["status"] == "not_configured"
    p = auth.put(f"/api/projects/{pid}/evm/config", json={"enabled": True, "bac": 50000, "cost_per_point": 400}).json()
    assert p["evm"]["enabled"] is True and p["evm"]["bac"] == 50000
    p = auth.post(f"/api/projects/{pid}/evm/baseline").json()
    cfg = p["evm"]
    assert cfg["baseline_locked_at"] is not None
    assert cfg["planned_points"] > 0 and cfg["planned_sprints"] >= 5 and cfg["start_date"] and cfg["end_date"]
    e = auth.get(f"/api/projects/{pid}/evm").json()
    assert e["status"] != "not_configured"
    assert e["ac"] == pytest.approx((9 + 13 + 12 + 5) * 400)  # completed points x cost_per_point
    s = auth.post(f"/api/projects/{pid}/evm/snapshot", json={"note": "test"}).json()
    assert s["as_of"] == TODAY.isoformat() and s["note"] == "test" and s["ev"] == e["ev"]
    s2 = auth.post(f"/api/projects/{pid}/evm/snapshot").json()
    assert s2["id"] == s["id"]  # upsert on the same day
    snaps = auth.get(f"/api/projects/{pid}/evm/snapshots").json()
    assert [x["id"] for x in snaps] == [s["id"]]
    assert "status" in s["metrics"] and "spi" in s["metrics"]
    e = auth.get(f"/api/projects/{pid}/evm").json()
    assert e["series"][-1]["sprint_id"] == data.sprints[4]  # snapshot row preferred on its date


def test_evm_daily_job_runs(data):
    evm.daily_snapshots()
    with session_scope() as db:
        snaps = evm.list_snapshots(db, db.get(Project, data.evm_project_id))
        assert len(snaps) == 1 and snaps[0].note == "daily"


# ---------------------------------------------------------------------------
# capacity
# ---------------------------------------------------------------------------


def test_learn_from_sprint(data):
    alex = data.users["Alex"]
    with session_scope() as db:
        for n in (1, 2, 3):
            capacity.learn_from_sprint(db, db.get(Sprint, data.sprints[n]))
        p = db.query(CapacityProfile).filter_by(project_id=data.project_id, user_id=alex).one()
        # Alex completed 3, 8, 5 points -> EWMA(0.4): 3 -> 5.0 -> 5.0
        assert p.sprints_observed == 3
        assert p.avg_points == pytest.approx(5.0, abs=0.01)
        assert p.confidence == pytest.approx(0.6)
        assert len(p.history) == 3 and p.history[-1]["sprint_name"] == "Sprint 3"
        assert p.stddev_points > 0
        assert p.points_per_hour > 0
        assert 0 < p.commitment_accuracy <= 1
        assert p.insights and any("sprint" in s.lower() or "commit" in s.lower() for s in p.insights)
        # re-learning the same sprint is idempotent
        capacity.learn_from_sprint(db, db.get(Sprint, data.sprints[3]))
        db.refresh(p)
        assert p.sprints_observed == 3


def test_project_capacity_and_sprint_capacity(auth, data):
    profiles = auth.get(f"/api/projects/{data.project_id}/capacity").json()
    assert {p["user_id"] for p in profiles} == set(data.users.values())
    assert all(p["user"]["name"] for p in profiles)

    sc = auth.get(f"/api/sprints/{data.sprints[5]}/capacity").json()
    assert sc["method"] == "points" and sc["team_count"] == 3
    assert sc["sprint"]["id"] == data.sprints[5]
    by_user = {e["user_id"]: e for e in sc["entries"]}
    alex = by_user[data.users["Alex"]]
    assert alex["available_hours"] == pytest.approx(40 * 2 * 0.7)  # 2-week sprint, no days off
    assert alex["suggested_points"] == pytest.approx(5.0, abs=0.1)
    assert alex["profile"]["sprints_observed"] == 3
    assert sc["team_points"] == pytest.approx(sum(e["suggested_points"] for e in sc["entries"]))

    sc = auth.put(
        f"/api/sprints/{data.sprints[5]}/capacity",
        json={"entries": [{"user_id": data.users["Blair"], "days_off": 2, "notes": "PTO"}]},
    ).json()
    blair = next(e for e in sc["entries"] if e["user_id"] == data.users["Blair"])
    assert blair["days_off"] == 2 and blair["notes"] == "PTO"
    assert blair["available_hours"] == pytest.approx((80 - 2 * 8) * 0.7)
    assert blair["suggested_points"] < alex["suggested_points"] * 1.5  # scaled down by availability


def test_plan_suggest_and_commit(auth, data):
    s = auth.get(f"/api/sprints/{data.sprints[5]}/plan/suggest")
    assert s.status_code == 200, s.text
    s = s.json()
    cand_ids = {c["id"] for c in s["candidates"]}
    assert data.backlog["epic"] not in cand_ids and data.backlog["feature"] not in cand_ids
    assert data.backlog["crit"] in cand_ids and data.backlog["blocked"] in cand_ids
    assert s["candidates"][0]["id"] == data.backlog["crit"]
    assert "critical priority" in s["candidates"][0]["reason"]
    assert all("score" in c and "reason" in c and "key" in c for c in s["candidates"])
    assert data.backlog["blocked"] not in s["recommended_ids"]
    team = s["capacity"]["team_points"]
    assert 0 < s["recommended_points"] <= team
    assert s["recommended_points"] == pytest.approx(sum(p["points"] for p in s["per_person"].values()))
    assert any(n.startswith("Team capacity") for n in s["notes"])
    assert any("Blair is out 2 days" == n for n in s["notes"])
    assert 0 <= s["confidence"] <= 1
    with session_scope() as db:
        ids = set(s["recommended_ids"])
        pts = sum(i.points or 0 for i in db.query(WorkItem).filter(WorkItem.id.in_(ids)))
    assert pts == pytest.approx(s["recommended_points"])

    r = auth.post(f"/api/sprints/{data.sprints[5]}/plan/commit", json={"item_ids": s["recommended_ids"]})
    assert r.status_code == 200, r.text
    sp = r.json()
    assert sp["capacity_points"] == pytest.approx(team) and sp["capacity_hours"] > 0
    with session_scope() as db:
        moved = db.query(WorkItem).filter(WorkItem.sprint_id == data.sprints[5]).all()
        assert {i.id for i in moved} == set(s["recommended_ids"])
        entries = db.query(CapacityEntry).filter_by(sprint_id=data.sprints[5]).all()
        planned = {e.user_id: e.planned_points for e in entries}
        alex_pts = sum(i.points or 0 for i in moved if i.assignee_id == data.users["Alex"])
        assert planned[data.users["Alex"]] == pytest.approx(alex_pts)


# ---------------------------------------------------------------------------
# retro
# ---------------------------------------------------------------------------


def test_retro_flow(auth, data):
    sid = data.sprints[3]
    r = auth.get(f"/api/sprints/{sid}/retro").json()
    assert r["state"] == "open" and r["sprint_id"] == sid and r["facilitator_id"] == data.users["Alex"]
    assert r["stats"]["committed"] == 17 and r["stats"]["completed"] == 12 and r["stats"]["carried_over"] == 2
    assert set(r) == {
        "id", "sprint_id", "project_id", "state", "went_well", "improve", "kudos", "actions", "mood",
        "agent_summary", "stats", "facilitator_id",
    }
    r = auth.post(f"/api/sprints/{sid}/retro/items", json={"column": "went_well", "text": "Pairing worked"}).json()
    entry = r["went_well"][0]
    assert len(entry["id"]) == 8 and entry["votes"] == 0 and entry["author_id"] == data.users["Alex"]
    r = auth.post(f"/api/sprints/{sid}/retro/vote", json={"column": "went_well", "entry_id": entry["id"]}).json()
    assert r["went_well"][0]["votes"] == 1
    r = auth.post(f"/api/sprints/{sid}/retro/mood", json={"score": 4}).json()
    assert r["mood"] == {data.users["Alex"]: 4}
    assert auth.post(f"/api/sprints/{sid}/retro/mood", json={"score": 9}).status_code == 422
    r = auth.post(
        f"/api/sprints/{sid}/retro/items",
        json={"column": "actions", "text": "Write ADRs for big changes", "owner_id": data.users["Blair"]},
    ).json()
    auth.post(f"/api/sprints/{sid}/retro/items", json={"column": "actions", "text": "Unowned action"})
    r = auth.post(f"/api/sprints/{sid}/retro/generate").json()
    # the agent package may supply its own wording; only the frozen numbers are guaranteed
    assert r["agent_summary"] and "12" in r["agent_summary"] and "17" in r["agent_summary"]
    assert r["stats"]["carried_over"] == 2

    r = auth.post(f"/api/sprints/{sid}/retro/close").json()
    assert r["state"] == "closed"
    owned = next(a for a in r["actions"] if a["owner_id"] == data.users["Blair"])
    assert owned["action_item_id"]
    with session_scope() as db:
        ai = db.get(ActionItem, owned["action_item_id"])
        assert ai.owner_id == data.users["Blair"] and ai.source == "retro" and ai.title == "Write ADRs for big changes"
        assert ai.project_id == data.project_id
        assert db.query(ActionItem).filter_by(owner_id=data.users["Alex"], source="retro").count() == 1
    # closed retros reject new entries
    assert auth.post(f"/api/sprints/{sid}/retro/items", json={"column": "improve", "text": "x"}).status_code == 400


def test_endpoints_require_login(client, data):
    client.post("/api/auth/logout")
    assert client.get(f"/api/projects/{data.project_id}/metrics/overview").status_code == 401
    assert client.get(f"/api/sprints/{data.sprints[3]}/retro").status_code == 401
    client.post("/api/auth/login", json={"user_id": data.users["Alex"]})


def test_services_run_without_core_modules(data):
    """Direct service calls (no routers) work and use the shared metrics helpers."""
    with session_scope() as db:
        project = db.get(Project, data.project_id)
        assert metrics.estimation(project) == "points"
        assert metrics.done_statuses(project) == {"done"}
        rep = evm.report(db, project)
        assert rep["status"] in ("on_track", "at_risk", "off_track")
        st = retro.stats(db, db.get(Sprint, data.sprints[2]))
        assert st["completed"] == 13 and st["carried_over"] == 0
