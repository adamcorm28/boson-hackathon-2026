import hashlib
import itertools
import json
import re
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import seed  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent.parent


class FakePaperclip:
    """Just enough of the Paperclip REST API (routes from docs/superpowers/spikes/paperclip-findings.md)."""

    def __init__(self):
        self.companies, self.goals, self.agents, self.issues = [], [], [], []
        self.requests: list[tuple[str, str, dict | None]] = []
        self._ids = itertools.count(1)

    def _new(self, prefix: str, body: dict) -> dict:
        return {"id": f"{prefix}-{next(self._ids)}", **body}

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        method, path = request.method, request.url.path
        self.requests.append((method, path, body))
        if path == "/api/companies":
            if method == "GET":
                return httpx.Response(200, json=self.companies)
            self.companies.append(self._new("co", body))
            return httpx.Response(201, json=self.companies[-1])
        if m := re.fullmatch(r"/api/companies/([^/]+)/(goals|agents|issues)", path):
            store = getattr(self, m.group(2))
            if method == "GET":
                return httpx.Response(200, json=[x for x in store if x["companyId"] == m.group(1)])
            if m.group(2) == "issues" and body.get("status") == "in_progress" and not body.get("assigneeAgentId"):
                return httpx.Response(400, json={"error": "in_progress issues require an assignee"})
            item = self._new(m.group(2)[:-1], {"companyId": m.group(1), "status": "paused", **body})
            store.append(item)
            return httpx.Response(201, json=item)
        if m := re.fullmatch(r"/api/agents/([^/]+)(/resume)?", path):
            agent = next(a for a in self.agents if a["id"] == m.group(1))
            if m.group(2):
                if agent["status"] != "paused":
                    return httpx.Response(409, json={"error": "agent is not paused"})
                agent["status"] = "idle"
            elif "instructionsBundle" in body:
                return httpx.Response(409, json={"error": "Unsupported configuration field"})
            else:
                agent.update(body)
            return httpx.Response(200, json=agent)
        if m := re.fullmatch(r"/api/agents/([^/]+)/instructions-bundle/file", path):
            agent = next(a for a in self.agents if a["id"] == m.group(1))
            files = agent["instructionsBundle"]["files"]
            revisions = agent.setdefault("revisions", {})
            if method == "GET":
                name = request.url.params["path"]
                content = files[name]
                revisions.setdefault(name, f"rev-{next(self._ids)}")
                return httpx.Response(200, json={
                    "path": name, "content": content,
                    "contentHash": hashlib.sha256(content.encode()).hexdigest(),
                    "revision": {"id": revisions[name]}})
            if "baseRevisionId" not in body:
                return httpx.Response(422, json={"code": "INSTRUCTION_BASE_REQUIRED"})
            if body["baseRevisionId"] != revisions.get(body["path"]):
                return httpx.Response(409, json={"error": "stale base revision"})
            files[body["path"]] = body["content"]
            revisions[body["path"]] = f"rev-{next(self._ids)}"
            return httpx.Response(200, json={"path": body["path"]})
        if re.fullmatch(r"/api/issues/[^/]+/comments", path):
            return httpx.Response(201, json={"id": f"comment-{next(self._ids)}", **body})
        return httpx.Response(404, json={"error": f"no fake route for {method} {path}"})

    def posts(self, suffix: str) -> list[dict]:
        return [b for m, p, b in self.requests if m == "POST" and p.endswith(suffix)]


@pytest.fixture
def fake():
    return FakePaperclip()


async def run_seed(fake: FakePaperclip, tmp_path: Path) -> dict:
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), base_url="http://paperclip") as client:
        return await seed.seed(
            client, repo_root=REPO_ROOT, demo_repo=tmp_path / "dunder-mifflin-infinity",
            artifacts_dir=tmp_path / "artifacts", gateway_url="http://localhost:8000",
            ids_path=tmp_path / "paperclip_ids.json",
        )


async def test_seed_creates_five_agents_with_reporting_lines(fake, tmp_path):
    ids = await run_seed(fake, tmp_path)
    posted = {b["name"]: b for b in fake.posts("/agents")}
    assert set(posted) == {"Michael Scott", "Kevin Malone", "Ryan Howard", "Dwight Schrute", "Jim Halpert"}
    assert all(b["adapterType"] == "claude_local" for b in posted.values())
    assert "reportsTo" not in posted["Michael Scott"]
    assert posted["Dwight Schrute"]["reportsTo"] == ids["agents"]["eng_lead"]
    assert posted["Jim Halpert"]["reportsTo"] == ids["agents"]["ceo"]
    assert posted["Dwight Schrute"]["role"] == "engineer" and posted["Jim Halpert"]["role"] == "general"
    assert posted["Dwight Schrute"]["adapterConfig"]["cwd"] == str(tmp_path / "dunder-mifflin-infinity")
    assert posted["Michael Scott"]["adapterConfig"]["cwd"] == str(REPO_ROOT)


async def test_seed_creates_company_and_goal(fake, tmp_path):
    await run_seed(fake, tmp_path)
    assert [c["name"] for c in fake.companies] == [seed.COMPANY_NAME]
    assert [g["title"] for g in fake.goals] == [seed.GOAL_TITLE]


async def test_instructions_placeholders_filled(fake, tmp_path):
    await run_seed(fake, tmp_path)
    for body in fake.posts("/agents"):
        text = body["instructionsBundle"]["files"]["AGENTS.md"]
        assert not re.findall(r"\{[A-Z_]+\}", text), body["name"]
        assert str(tmp_path / "artifacts") in text


async def test_agents_resumed(fake, tmp_path):
    await run_seed(fake, tmp_path)
    assert all(a["status"] == "idle" for a in fake.agents)


async def test_seed_issues_unassigned_with_owner_footer(fake, tmp_path):
    await run_seed(fake, tmp_path)
    issues = fake.posts("/issues")
    assert len(issues) == len(json.loads((REPO_ROOT / "backend/company/data/issues_seed.json").read_text()))
    assert all(not b.get("assigneeAgentId") for b in issues)
    bug = next(b for b in issues if "bulk discount" in b["title"])
    assert bug["description"].endswith("---\norigin: seed\nowner: eng_lead")
    assert bug["priority"] == "critical"


async def test_in_progress_seeded_as_todo(fake, tmp_path):
    await run_seed(fake, tmp_path)
    expenses = next(b for b in fake.posts("/issues") if "expense reports" in b["title"])
    assert expenses["status"] == "todo"


async def test_seed_comments_carry_author_name(fake, tmp_path):
    await run_seed(fake, tmp_path)
    assert any(b["body"].startswith("Ryan Howard: ") for b in fake.posts("/comments"))


async def test_ids_file_written_keyed_by_seed_task_id(fake, tmp_path):
    ids = await run_seed(fake, tmp_path)
    assert json.loads((tmp_path / "paperclip_ids.json").read_text()) == ids
    assert set(ids["agents"]) == {"ceo", "cfo", "eng_lead", "engineer", "sales_lead"}
    assert "DM-101" in ids["issues"]


async def test_seed_is_idempotent(fake, tmp_path):
    first = await run_seed(fake, tmp_path)
    fake.requests.clear()
    second = await run_seed(fake, tmp_path)
    assert second == first
    assert not [p for m, p, _ in fake.requests if m == "POST" and not p.endswith("/resume")]
    assert len(fake.agents) == 5 and len(fake.companies) == 1


async def test_rerun_refreshes_instructions_via_file_put(fake, tmp_path):
    await run_seed(fake, tmp_path)
    for agent in fake.agents:
        agent["instructionsBundle"]["files"]["AGENTS.md"] = "stale"
    await run_seed(fake, tmp_path)
    assert all("RESULT:" in a["instructionsBundle"]["files"]["AGENTS.md"] for a in fake.agents)


async def test_rerun_skips_unchanged_instructions(fake, tmp_path):
    await run_seed(fake, tmp_path)
    fake.requests.clear()
    await run_seed(fake, tmp_path)
    assert not [p for m, p, _ in fake.requests if m == "PUT"]


async def test_resume_tolerates_agent_already_running(fake, tmp_path):
    # Paperclip auto-readies new agents within seconds; resuming one that isn't paused returns 409.
    original = fake.handler

    def auto_ready(request):
        response = original(request)
        if request.method == "POST" and request.url.path.endswith("/agents"):
            fake.agents[-1]["status"] = "idle"
        return response

    fake.handler = auto_ready
    ids = await run_seed(fake, tmp_path)
    assert len(ids["agents"]) == 5


def test_render_rejects_unknown_placeholder():
    with pytest.raises(KeyError):
        seed.render("hello {NOPE}", {"ARTIFACTS_DIR": "/x"})
