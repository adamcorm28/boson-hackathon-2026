import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from company.types import Artifact, TaskResult
from gateway import app_state, http
from gateway.events import EventBus


@pytest.fixture
def client(monkeypatch, roles, company):
    monkeypatch.setattr(app_state, "roles", roles)
    monkeypatch.setattr(app_state, "company", company)
    monkeypatch.setattr(app_state, "bus", EventBus())
    app = FastAPI()
    app.include_router(http.router)
    return TestClient(app)


def test_get_roles(client):
    body = client.get("/roles").json()
    assert {r["id"] for r in body} == {"ceo", "cfo", "eng_lead", "engineer", "sales_lead"}
    assert set(body[0]) == {"id", "name", "title", "reports_to", "voice", "sprite", "desk"}


def test_board_has_all_columns(client, company):
    company.set_status("DM-101", "in_review")
    cols = client.get("/board").json()["columns"]
    assert set(cols) == {"backlog", "todo", "in_progress", "in_review", "blocked", "done"}
    card = next(c for c in cols["in_review"] if c["task_id"] == "DM-101")
    assert set(card) == {"task_id", "title", "assignee_role", "status", "origin"}
    assert all(c["status"] == s for s, cards in cols.items() for c in cards)


def test_task_404(client):
    assert client.get("/tasks/DM-999999").status_code == 404


def test_task_without_result(client):
    body = client.get("/tasks/DM-101").json()
    assert body["result_summary"] is None and body["artifacts"] == []


async def test_task_result_parsed(client, company):
    tid = await company.create_task("engineer", "Fix bulk discount", "b", "eng_lead")
    company.complete(tid, "Fixed the discount.", (Artifact("diff", "http://localhost:8000/artifacts/x.diff", "The fix"),))
    body = client.get(f"/tasks/{tid}").json()
    assert body["result_summary"] == "Fixed the discount."
    assert body["artifacts"] == [{"kind": "diff", "url": "http://localhost:8000/artifacts/x.diff", "label": "The fix"}]
    assert body["status"] == "done" and body["assignee_role"] == "engineer"


async def drain(sub):
    import asyncio
    out = []
    while True:
        try:
            out.append(await asyncio.wait_for(sub.get(), 0.01))
        except asyncio.TimeoutError:
            return out


@pytest.fixture
def state(monkeypatch, roles, company):
    from gateway.injector import NotificationQueue

    monkeypatch.setattr(app_state, "roles", roles)
    monkeypatch.setattr(app_state, "company", company)
    monkeypatch.setattr(app_state, "bus", EventBus())
    monkeypatch.setattr(app_state, "queue", NotificationQueue())
    monkeypatch.setattr(app_state, "active_call", None)
    monkeypatch.setattr(app_state, "watcher", None)
    return app_state


def result(tid="DM-200"):
    return TaskResult(tid, "Fix bulk discount", "engineer", "eng_lead", "Fixed it.", [])


async def test_on_complete_with_no_call_publishes_null_ping(state):
    sub = state.bus.subscribe()
    await state.on_complete(result())
    events = await drain(sub)
    assert [t for t, _ in events] == ["task.completed", "ping"]
    assert events[0][1] == {"task_id": "DM-200", "from_role": "engineer", "title": "Fix bulk discount", "summary": "Fixed it."}
    assert events[1][1]["to_role"] is None and events[1][1]["from_role"] == "engineer"
    assert [r.task_id for r in state.queue.pending()] == ["DM-200"]


async def test_on_complete_during_call_queues_without_ping(state, monkeypatch, roles):
    monkeypatch.setattr(app_state, "active_call", type("S", (), {"role": roles["sales_lead"]})())
    sub = state.bus.subscribe()
    await state.on_complete(result())
    assert [t for t, _ in await drain(sub)] == ["task.completed"]
    assert len(state.queue) == 1


async def test_on_update_publishes_task_and_agent_status(state, company):
    tid = await company.create_task("engineer", "Fix bulk discount", "b", "eng_lead")
    company.set_status(tid, "in_progress")
    sub = state.bus.subscribe()
    await state.on_update(await company.get_issue(tid))
    events = await drain(sub)
    assert events[0] == ("task.updated", {"task_id": tid, "status": "in_progress", "assignee_role": "engineer", "title": "Fix bulk discount"})
    assert events[1] == ("agent.status", {"role": "engineer", "state": "working"})


async def test_completion_with_no_call_publishes_null_ping(state, company):
    watcher_mod = pytest.importorskip("company.watcher")  # runs once B9 lands
    tid = await company.create_task("engineer", "Fix bulk discount", "b", "eng_lead")
    w = watcher_mod.TaskWatcher(company, state.on_update, state.on_complete)
    await w.poll_once()
    sub = state.bus.subscribe()
    company.complete(tid, "Fixed it.")
    await w.poll_once()
    events = await drain(sub)
    types = [t for t, _ in events]
    assert types.index("task.completed") < types.index("ping")
    assert dict(events)["ping"]["to_role"] is None


def test_dev_complete_announces(state, company):
    app = FastAPI()
    app.include_router(http.router)
    sub = state.bus.subscribe()
    r = TestClient(app).post("/dev/complete/DM-101", params={"summary": "Patched pricing.js."})
    assert r.status_code == 200
    assert TestClient(app).get("/tasks/DM-101").json()["result_summary"] == "Patched pricing.js."
    assert [r.task_id for r in state.queue.pending()] == ["DM-101"]
    assert sub._queue.qsize() == 2  # task.completed + ping


async def test_failed_completion_is_flagged_and_pings_couldnt_finish(state):
    sub = state.bus.subscribe()
    await state.on_complete(TaskResult("DM-201", "Lackawanna model", "cfo", "ceo", "It couldn't finish.", [], failed=True))
    events = dict(await drain(sub))
    assert events["task.completed"]["failed"] is True
    assert "couldn't finish" in events["ping"]["text"] and "is done" not in events["ping"]["text"]
