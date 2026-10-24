import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from company.types import Artifact
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
