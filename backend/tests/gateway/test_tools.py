import pytest

from company.types import VOICE_TOOL_NAMES, CompanyUnavailable
from gateway.tools import TOOL_SCHEMAS, CallContext, run_tool, tools_for


def make_ctx(roles, company, role_id, started=None):
    async def on_task_started(task_id, title, assignee_role):
        if started is not None:
            started.append((task_id, title, assignee_role))

    return CallContext(role=roles[role_id], company=company, roles=roles, on_task_started=on_task_started)


def test_schemas_cover_all_tool_names():
    assert set(TOOL_SCHEMAS) == VOICE_TOOL_NAMES
    for name, schema in TOOL_SCHEMAS.items():
        if name != "web_search":
            assert schema["type"] == "function" and schema["name"] == name
            assert schema["parameters"]["type"] == "object"


def test_tools_for_web_search_is_server_tool(roles):
    tools = tools_for(roles["eng_lead"])
    assert {"type": "web_search"} in tools
    assert len(tools) == len(roles["eng_lead"].voice_tools)


async def test_delegate_creates_voice_task_and_notifies(roles, company):
    started = []
    ctx = make_ctx(roles, company, "eng_lead", started)
    out = await run_tool("delegate_task", {"assignee": "engineer", "title": "Fix bulk discount", "brief": "b"}, ctx)
    assert out["status"] == "started"
    assert out["assignee_name"] == "Dwight Schrute"
    assert len(started) == 1 and started[0][0] == out["task_id"]
    issue = await company.get_issue(out["task_id"])
    assert issue.requested_by_role == "eng_lead"
    assert issue.origin == "voice"


async def test_delegate_disallowed_assignee_returns_error(roles, company):
    # engineer has no delegate_task at all; give it a role that has the tool but not the target
    ctx = make_ctx(roles, company, "sales_lead")
    before = len(await company.list_issues())
    out = await run_tool("delegate_task", {"assignee": "engineer", "title": "x", "brief": "y"}, ctx)
    assert "error" in out
    assert len(await company.list_issues()) == before


async def test_tool_not_in_role_returns_error(roles, company):
    ctx = make_ctx(roles, company, "engineer")
    out = await run_tool("delegate_task", {"assignee": "sales_lead", "title": "x", "brief": "y"}, ctx)
    assert "error" in out


async def test_unknown_tool_returns_error(roles, company):
    out = await run_tool("launch_missiles", {}, make_ctx(roles, company, "ceo"))
    assert "error" in out


async def test_get_issue_unknown_returns_error(roles, company):
    out = await run_tool("get_issue", {"task_id": "DM-999999"}, make_ctx(roles, company, "eng_lead"))
    assert "error" in out


async def test_overview_includes_flags(roles, company, fake_data_tools):
    out = await run_tool("get_company_overview", {}, make_ctx(roles, company, "ceo"))
    assert out["monthly_sales"] == 700000
    assert any("bulk discount" in f["title"].lower() for f in out["flags"])


async def test_get_board_uses_character_names(roles, company):
    out = await run_tool("get_board", {}, make_ctx(roles, company, "ceo"))
    bulk = next(t for t in out["tasks"] if "bulk discount" in t["title"].lower())
    assert bulk["assignee"] == "Ryan Howard"
    assert set(bulk) == {"task_id", "title", "status", "assignee"}


async def test_get_my_work(roles, company):
    out = await run_tool("get_my_work", {}, make_ctx(roles, company, "eng_lead"))
    assert out["status"]["role"] == "eng_lead"
    assert any("bulk discount" in i["title"].lower() for i in out["issues"])


async def test_unknown_email_and_deal_return_error(roles, company, fake_data_tools):
    assert "error" in await run_tool("read_email", {"email_id": "nope"}, make_ctx(roles, company, "ceo"))
    assert "error" in await run_tool("get_deal", {"name": "Acme"}, make_ctx(roles, company, "sales_lead"))
    deal = await run_tool("get_deal", {"name": "lackawanna"}, make_ctx(roles, company, "sales_lead"))
    assert deal["account"].startswith("Lackawanna")


async def test_company_unavailable_returns_error(roles):
    class Down:
        async def list_issues(self, role=None, status=None):
            raise CompanyUnavailable()

    out = await run_tool("get_board", {}, make_ctx(roles, Down(), "ceo"))
    assert "error" in out


@pytest.mark.parametrize("name", ["get_ai_spend"])
async def test_ai_spend(roles, company, name):
    out = await run_tool(name, {}, make_ctx(roles, company, "cfo"))
    assert out["total_cents"] == 412
