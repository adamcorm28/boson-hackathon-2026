import pytest

import company
from company.mock import MockCompany


@pytest.fixture
def c():
    return MockCompany()


async def test_list_issues_filters_by_role_and_status(c):
    eng = await c.list_issues(role="eng_lead")
    assert any("bulk discount" in i.title.lower() for i in eng)
    assert all(i.assignee_role == "eng_lead" for i in eng)

    blocked = await c.list_issues(status="blocked")
    assert blocked
    assert all(i.status == "blocked" for i in blocked)


async def test_create_task_marks_voice_origin(c):
    tid = await c.create_task("engineer", "Fix bulk discount", "brief", "eng_lead")
    issue = await c.get_issue(tid)
    assert issue.origin == "voice"
    assert issue.requested_by_role == "eng_lead"
    assert issue.status == "todo"
    assert issue.assignee_role == "engineer"


async def test_get_issue_unknown_raises_keyerror(c):
    with pytest.raises(KeyError):
        await c.get_issue("DM-999999")


async def test_agent_status_working_when_in_progress(c):
    tid = await c.create_task("engineer", "Fix bulk discount", "brief", "eng_lead")
    c.set_status(tid, "in_progress")
    status = await c.get_agent_status("engineer")
    assert status.state == "working"
    assert status.current_task_id == tid


async def test_complete_hook_adds_result_comment(c):
    tid = await c.create_task("engineer", "Fix bulk discount", "brief", "eng_lead")
    c.complete(tid, "Fixed the discount.")
    issue = await c.get_issue(tid)
    assert issue.comments[-1].body.startswith("RESULT: ")
    assert issue.status == "done"


def test_get_company_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("COMPANY_BACKEND", raising=False)
    monkeypatch.setattr(company, "_instance", None)
    assert isinstance(company.get_company(), MockCompany)


async def test_fail_hook_sets_failed_reason(c):
    tid = await c.create_task("cfo", "Model", "brief", "ceo")
    c.fail(tid, "acpx_turn_failed")
    assert (await c.get_issue(tid)).failed_reason == "acpx_turn_failed"
    assert (await c.get_issue("DM-101")).failed_reason is None


async def test_research_task_kind(c):
    tid = await c.create_task("cfo", "Research: competitor financials", "q", "cfo", kind="research")
    assert (await c.get_issue(tid)).kind == "research"
    assert (await c.get_issue("DM-101")).kind == "task"
