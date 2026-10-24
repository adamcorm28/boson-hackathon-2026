from company.types import CompanyUnavailable, TaskResult
from gateway.instructions import build_briefing, build_instructions, greeting_instructions


async def test_instructions_contain_persona_and_rules(roles):
    text = build_instructions(roles["eng_lead"], "## Briefing\nnothing")
    assert roles["eng_lead"].persona.strip() in text
    assert "never read out IDs or URLs" in text
    assert "at most one comedy bit" in text
    assert "delegate_task" in text
    assert text.index("Speaking style") < text.index("Tools") < text.index("## Briefing") < text.index("Call start")
    assert f"Answer the call in character with: {roles['eng_lead'].greeting}" in text


async def test_briefing_lists_own_open_issues_only(roles, company):
    text = await build_briefing(roles["eng_lead"], company, [], [], roles)
    assert "bulk discount" in text.lower()
    assert "DM-101" in text
    assert "Q4 numbers for David Wallace" not in text


async def test_briefing_excludes_done_issues(roles, company):
    company.set_status("DM-101", "done")
    text = await build_briefing(roles["eng_lead"], company, [], [], roles)
    assert "DM-101" not in text


async def test_ceo_briefing_has_flags(roles, company):
    ceo = await build_briefing(roles["ceo"], company, [], [], roles)
    assert "Flagged across the company" in ceo
    assert "bulk discount" in ceo.lower()
    jim = await build_briefing(roles["sales_lead"], company, [], [], roles)
    assert "Flagged across the company" not in jim


async def test_briefing_includes_recent_calls(roles, company):
    calls = ["With Ryan Howard (3 min ago): talked about the bug.", "b", "c", "d"]
    text = await build_briefing(roles["sales_lead"], company, calls, [], roles)
    assert "With Ryan Howard (3 min ago)" in text
    assert "- d" not in text


async def test_briefing_includes_pending_results(roles, company):
    pending = [TaskResult("DM-200", "Fix bulk discount", "engineer", "eng_lead", "Fixed it.", [])]
    text = await build_briefing(roles["eng_lead"], company, [], pending, roles)
    assert "Fix bulk discount" in text
    assert "Dwight Schrute" in text


async def test_briefing_survives_company_unavailable(roles):
    class Down:
        async def list_issues(self, role=None, status=None):
            raise CompanyUnavailable()

    text = await build_briefing(roles["ceo"], Down(), [], [], roles)
    assert "(task board unavailable right now)" in text


def test_greeting(roles):
    assert greeting_instructions(roles["ceo"]) == (
        "Answer the call in character with: Michael Scott, World's Best Boss. Talk to me."
    )


async def test_briefing_lists_delegation_targets(roles, company):
    text = await build_briefing(roles["eng_lead"], company, [], [], roles)
    assert 'Dwight Schrute: assignee "engineer"' in text
    dwight = await build_briefing(roles["engineer"], company, [], [], roles)
    assert 'Dwight Schrute: assignee "engineer" (your own work body' in dwight


def test_tool_rules_route_outside_questions_to_research():
    from gateway.instructions import TOOL_RULES
    assert "research" in TOOL_RULES
    assert "competitors" in TOOL_RULES and "our own business" in TOOL_RULES


async def test_briefing_lists_finished_research(roles, company):
    tid = await company.create_task("cfo", "Research: finance tools", "q", "cfo", kind="research")
    company.complete(tid, "Three tools stand out.")
    text = await build_briefing(roles["cfo"], company, [], [], roles)
    assert "## Research you finished recently" in text
    assert "Research: finance tools" in text and "Three tools stand out." in text


def test_tool_rules_answer_finished_research_from_briefing():
    from gateway.instructions import TOOL_RULES
    assert "answer right away from the summary in your briefing" in TOOL_RULES
