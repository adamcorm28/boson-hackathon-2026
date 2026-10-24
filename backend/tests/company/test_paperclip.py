import json
import re

import httpx
import pytest

import company
from company.paperclip import PaperclipCompany
from company.types import CompanyUnavailable

CID = "co-1"
IDS = {
    "company_id": CID,
    "agents": {"ceo": "ag-ceo", "cfo": "ag-cfo", "eng_lead": "ag-eng", "engineer": "ag-dwight", "sales_lead": "ag-jim"},
    "issues": {"DM-101": "is-1", "DM-103": "is-3"},
}


def issue(id_, identifier, title, status="todo", assignee=None, footer="", priority="medium"):
    return {"id": id_, "identifier": identifier, "title": title, "status": status, "priority": priority,
            "assigneeAgentId": assignee, "description": "Brief." + footer, "updatedAt": "2026-10-24T05:00:00Z"}


SEED_FOOTER = "\n\n---\norigin: seed\nowner: eng_lead"
VOICE_FOOTER = "\n\n---\norigin: voice\nrequested_by: eng_lead"


class FakePaperclip:
    def __init__(self):
        self.issues = [
            issue("is-1", "DUNA-1", "Infinity checkout not applying bulk discount", footer=SEED_FOOTER, priority="critical"),
            issue("is-3", "DUNA-3", "Lackawanna County quote on hold", status="blocked",
                  footer="\n\n---\norigin: seed\nowner: sales_lead"),
            issue("is-11", "DUNA-11", "Fix bulk discount", status="in_progress", assignee="ag-dwight", footer=VOICE_FOOTER),
        ]
        self.comments = {"is-11": [
            {"authorType": "agent", "authorAgentId": "ag-dwight", "body": "Found the root cause.", "createdAt": "t1"},
            {"authorType": "agent", "authorAgentId": "ag-dwight", "body": "x" * 400, "createdAt": "t2"},
        ]}
        self.posted: list[tuple[str, dict]] = []

    def find(self, key):
        return next((i for i in self.issues if key in (i["id"], i["identifier"])), None)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        if method == "POST":
            self.posted.append((path, body))
        if path == f"/api/companies/{CID}/issues":
            if method == "GET":
                return httpx.Response(200, text=json.dumps(self.issues))
            new = issue(f"is-{len(self.issues) + 20}", f"DUNA-{len(self.issues) + 20}", body["title"],
                        assignee=body["assigneeAgentId"], footer="")
            new["description"] = body["description"]
            self.issues.append(new)
            return httpx.Response(201, json=new)
        if m := re.fullmatch(r"/api/issues/([^/]+)(/comments)?", path):
            found = self.find(m.group(1))
            if found is None:
                return httpx.Response(404, json={"error": "not found"})
            if m.group(2):
                if method == "POST":
                    self.comments.setdefault(found["id"], []).append({"authorType": "user", "body": body["body"]})
                    return httpx.Response(201, json={})
                return httpx.Response(200, json=self.comments.get(found["id"], []))
            return httpx.Response(200, json=found)
        if path == f"/api/companies/{CID}/costs/by-agent":
            return httpx.Response(200, json=[
                {"agentId": "ag-dwight", "costCents": 0, "inputTokens": 1000, "cachedInputTokens": 5000, "outputTokens": 200},
                {"agentId": "ag-jim", "costCents": 3, "inputTokens": 500, "cachedInputTokens": 0, "outputTokens": 100},
            ])
        return httpx.Response(404, json={"error": f"no fake route {method} {path}"})


@pytest.fixture
def fake():
    return FakePaperclip()


@pytest.fixture
def pc(fake):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), base_url="http://paperclip")
    return PaperclipCompany("http://paperclip", IDS, client=client)


async def test_list_issues_maps_roles_and_origin(pc):
    issues = {i.task_id: i for i in await pc.list_issues()}
    assert set(issues) == {"DM-101", "DM-103", "DUNA-11"}
    seed_bug, voice = issues["DM-101"], issues["DUNA-11"]
    assert (seed_bug.origin, seed_bug.assignee_role, seed_bug.requested_by_role) == ("seed", "eng_lead", None)
    assert seed_bug.flagged and seed_bug.description == "Brief."
    assert (voice.origin, voice.assignee_role, voice.requested_by_role) == ("voice", "engineer", "eng_lead")
    assert not voice.flagged


async def test_list_issues_filters_by_role_and_status(pc):
    assert [i.task_id for i in await pc.list_issues(role="sales_lead")] == ["DM-103"]
    assert [i.task_id for i in await pc.list_issues(status="in_progress")] == ["DUNA-11"]


async def test_get_issue_accepts_seed_id_and_identifier_with_comments(pc):
    seed_bug = await pc.get_issue("DM-101")
    assert seed_bug.title.startswith("Infinity checkout")
    voice = await pc.get_issue("DUNA-11")
    assert [c.author_role for c in voice.comments] == ["engineer", "engineer"]


async def test_get_issue_404_raises_keyerror(pc):
    with pytest.raises(KeyError):
        await pc.get_issue("DUNA-999")


async def test_create_task_posts_assignee_and_footer(pc, fake):
    task_id = await pc.create_task("engineer", "Fix bulk discount", "Checkout ignores the 10% rule.", "eng_lead")
    path, body = fake.posted[-1]
    assert path == f"/api/companies/{CID}/issues"
    assert body["assigneeAgentId"] == IDS["agents"]["engineer"]
    assert body["description"].endswith("---\norigin: voice\nrequested_by: eng_lead")
    assert body["status"] == "todo"
    created = await pc.get_issue(task_id)
    assert created.origin == "voice" and created.description == "Checkout ignores the 10% rule."


async def test_add_comment(pc, fake):
    await pc.add_comment("DM-101", "Call note: discussed the fix.")
    assert fake.posted[-1] == ("/api/issues/is-1/comments", {"body": "Call note: discussed the fix."})


async def test_agent_status_working_with_truncated_last_comment(pc):
    status = await pc.get_agent_status("engineer")
    assert status.state == "working" and status.current_task_id == "DUNA-11"
    assert len(status.last_comment) == 300


async def test_agent_status_idle(pc):
    status = await pc.get_agent_status("cfo")
    assert (status.state, status.current_task_id, status.last_comment) == ("idle", None, None)


async def test_get_costs_reports_billed_cents_and_tokens(pc):
    costs = await pc.get_costs()
    assert costs["total_cents"] == 3
    assert costs["by_role"] == {"engineer": 0, "sales_lead": 3}
    assert costs["tokens"]["by_role"]["engineer"] == {"input": 1000, "cached_input": 5000, "output": 200}


async def test_get_costs_includes_api_list_price_estimate(pc, monkeypatch):
    monkeypatch.delenv("PAPERCLIP_PRICING_MODEL", raising=False)
    est = (await pc.get_costs())["estimate"]
    # Claude Opus 5.5 list prices: $4/M input, $0.20/M cached input, $20/M output
    assert est["model"] == "claude-opus-5-5"
    assert est["by_role_usd"] == {"engineer": 0.009, "sales_lead": 0.004}
    assert est["total_usd"] == 0.013
    assert "list prices" in est["basis"]


async def test_get_costs_estimate_with_other_pricing_model(pc, monkeypatch):
    monkeypatch.setenv("PAPERCLIP_PRICING_MODEL", "claude-sonnet-5-5")
    est = (await pc.get_costs())["estimate"]
    assert est["model"] == "claude-sonnet-5-5"
    assert est["total_usd"] == 0.007  # 1500*$2/M + 5000*$0.20/M + 300*$10/M


async def test_get_costs_unknown_pricing_model_skips_estimate(pc, monkeypatch):
    monkeypatch.setenv("PAPERCLIP_PRICING_MODEL", "claude-mystery-9")
    assert (await pc.get_costs())["estimate"] is None


async def test_timeout_raises_company_unavailable():
    def boom(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    pc = PaperclipCompany("http://paperclip", IDS, client=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    with pytest.raises(CompanyUnavailable):
        await pc.list_issues()


async def test_server_error_raises_company_unavailable():
    pc = PaperclipCompany("http://paperclip", IDS, client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")), base_url="http://paperclip"))
    with pytest.raises(CompanyUnavailable):
        await pc.get_agent_status("ceo")


async def test_raw_control_characters_in_reply_are_tolerated(fake, pc):
    fake.issues[0]["title"] = "Tab\there"
    original = fake.handler

    def raw(request):
        resp = original(request)
        return httpx.Response(resp.status_code, text=resp.text.replace("\\t", "\t"))

    pc._client = httpx.AsyncClient(transport=httpx.MockTransport(raw), base_url="http://paperclip")
    assert (await pc.get_issue("DM-101")).title == "Tab\there"


def test_from_env_reads_ids_file(tmp_path, monkeypatch):
    ids_path = tmp_path / "paperclip_ids.json"
    ids_path.write_text(json.dumps(IDS))
    monkeypatch.setenv("PAPERCLIP_URL", "http://example:3100")
    pc = PaperclipCompany.from_env(ids_path=ids_path)
    assert pc.base_url == "http://example:3100" and pc.ids == IDS


def test_from_env_without_seed_explains(tmp_path):
    with pytest.raises(RuntimeError, match="seed.py"):
        PaperclipCompany.from_env(ids_path=tmp_path / "missing.json")


def test_get_company_selects_paperclip(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPANY_BACKEND", "paperclip")
    monkeypatch.setattr(company, "_instance", None)
    monkeypatch.setattr("company.paperclip.DEFAULT_IDS_PATH", tmp_path / "ids.json")
    (tmp_path / "ids.json").write_text(json.dumps(IDS))
    assert isinstance(company.get_company(), PaperclipCompany)
