import json
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import reset_demo  # noqa: E402
import seed  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent.parent
SEED_ISSUES = json.loads((REPO_ROOT / "backend/company/data/issues_seed.json").read_text())
NAMES = {"eng_lead": "Ryan Howard", "sales_lead": "Jim Halpert", "cfo": "Kevin Malone"}


class FakePaperclip:
    """Dunder Mifflin after a demo take: voice tasks, touched seed issues, a live run."""

    def __init__(self):
        self.company = {"id": "co-1", "name": seed.COMPANY_NAME}
        self.agents = [{"id": f"ag-{i}", "name": n} for i, n in enumerate(
            ["Michael Scott", "Kevin Malone", "Ryan Howard", "Dwight Schrute", "Jim Halpert"])]
        self.issues, self.comments = [], {}
        for n, raw in enumerate(SEED_ISSUES):
            issue_id = f"is-{n}"
            self.issues.append({"id": issue_id, "title": raw["title"],
                                "status": "todo" if raw["status"] == "in_progress" else raw["status"],
                                "description": raw["description"] + seed.seed_footer(raw["assignee_role"])})
            self.comments[issue_id] = [{"id": f"{issue_id}-c{k}", "body": f"{NAMES.get(c['author_role'], 'Board')}: {c['body']}"}
                                       for k, c in enumerate(raw.get("comments", []))]
        # what a take leaves behind
        self.issues[0]["status"] = "in_progress"
        self.comments["is-0"].append({"id": "is-0-note", "body": "Call note: discussed the bulk discount fix."})
        self.issues += [
            {"id": "is-v1", "title": "Fix bulk discount", "status": "done",
             "description": "Brief.\n\n---\norigin: voice\nrequested_by: eng_lead"},
            {"id": "is-v2", "title": "Prospect deck", "status": "in_progress",
             "description": "Brief.\n\n---\norigin: voice\nrequested_by: sales_lead"},
            {"id": "is-v3", "title": "Old task", "status": "cancelled",
             "description": "Brief.\n\n---\norigin: voice\nrequested_by: ceo"},
        ]
        self.runs = [{"id": "run-1", "status": "running"}, {"id": "run-2", "status": "succeeded"}]
        self.requests: list[tuple[str, str, dict | None]] = []

    def issue(self, issue_id):
        return next(i for i in self.issues if i["id"] == issue_id)

    def handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((method, path, body))
        if path == "/api/companies":
            return httpx.Response(200, json=[{"id": "x", "name": "Spike Co"}, self.company])
        if path == "/api/companies/co-1/agents":
            return httpx.Response(200, json=self.agents)
        if path == "/api/companies/co-1/issues":
            return httpx.Response(200, text=json.dumps(self.issues))
        if path == "/api/companies/co-1/heartbeat-runs":
            return httpx.Response(200, json=self.runs)
        if m := re.fullmatch(r"/api/heartbeat-runs/([^/]+)/cancel", path):
            next(r for r in self.runs if r["id"] == m.group(1))["status"] = "cancelled"
            return httpx.Response(200, json={})
        if m := re.fullmatch(r"/api/agents/([^/]+)/runtime-state/reset-session", path):
            return httpx.Response(200, json={})
        if m := re.fullmatch(r"/api/issues/([^/]+)", path):
            self.issue(m.group(1)).update(body)
            return httpx.Response(200, json=self.issue(m.group(1)))
        if m := re.fullmatch(r"/api/issues/([^/]+)/comments", path):
            return httpx.Response(200, json=self.comments.get(m.group(1), []))
        if m := re.fullmatch(r"/api/issues/([^/]+)/comments/([^/]+)", path):
            self.comments[m.group(1)] = [c for c in self.comments[m.group(1)] if c["id"] != m.group(2)]
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": f"no fake route {method} {path}"})


@pytest.fixture
def fake():
    return FakePaperclip()


async def run_reset(fake):
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), base_url="http://paperclip") as client:
        return await reset_demo.reset_paperclip(client, repo_root=REPO_ROOT)


async def test_cancels_voice_tasks_but_not_seed_issues(fake):
    summary = await run_reset(fake)
    assert {i["id"]: i["status"] for i in fake.issues if i["id"].startswith("is-v")} == {
        "is-v1": "cancelled", "is-v2": "cancelled", "is-v3": "cancelled"}
    assert summary["voice_tasks_cancelled"] == 2  # is-v3 was already cancelled


async def test_restores_seed_status_and_removes_extra_comments(fake):
    summary = await run_reset(fake)
    assert fake.issue("is-0")["status"] == "todo"
    assert [c["id"] for c in fake.comments["is-0"]] == ["is-0-c0"]
    assert summary == {**summary, "seed_issues_restored": 1, "comments_deleted": 1}


async def test_cancels_only_active_runs(fake):
    summary = await run_reset(fake)
    cancelled = [p for m, p, _ in fake.requests if p.endswith("/cancel")]
    assert cancelled == ["/api/heartbeat-runs/run-1/cancel"]
    assert summary["runs_cancelled"] == 1


async def test_resets_every_agent_session(fake):
    summary = await run_reset(fake)
    resets = {p.split("/")[3] for m, p, _ in fake.requests if p.endswith("/reset-session")}
    assert resets == {a["id"] for a in fake.agents}
    assert summary["sessions_reset"] == 5


async def test_runs_cancelled_before_tasks(fake):
    await run_reset(fake)
    order = [p for m, p, _ in fake.requests if m in ("POST", "PATCH")]
    assert order[0] == "/api/heartbeat-runs/run-1/cancel"


async def test_missing_company_is_a_noop(fake):
    fake.company["name"] = "Someone Else"
    summary = await run_reset(fake)
    assert summary["company_found"] is False
    assert not [r for r in fake.requests if r[0] != "GET"]


class FakeRun:
    def __init__(self, outputs=None):
        self.commands, self.outputs = [], outputs or {}

    def __call__(self, cmd, **kwargs):
        self.commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=self.outputs.get(tuple(cmd[:4]), ""), stderr="")


def test_reset_repo_checks_out_main_resets_and_deletes_fix_branches(tmp_path):
    run = FakeRun({("git", "-C", str(tmp_path), "branch"): "  fix/bulk-discount\n* main\n  fix/other\n"})
    reset_demo.reset_repo(tmp_path, run=run)
    assert ["git", "-C", str(tmp_path), "checkout", "-q", "-f", "main"] in run.commands
    assert ["git", "-C", str(tmp_path), "reset", "-q", "--hard", "seeded-bug"] in run.commands
    assert ["git", "-C", str(tmp_path), "branch", "-D", "fix/bulk-discount", "fix/other"] in run.commands


def test_reset_github_closes_prs_and_deletes_remote_fix_branches(tmp_path):
    run = FakeRun({
        ("gh", "pr", "list", "--repo"): json.dumps([{"number": 7}]),
        ("git", "-C", str(tmp_path), "ls-remote"): "abc\trefs/heads/fix/bulk-discount\ndef\trefs/heads/main\n",
    })
    reset_demo.reset_github(tmp_path, "thomas-m1/dunder-mifflin-infinity", run=run)
    assert ["gh", "pr", "close", "7", "--repo", "thomas-m1/dunder-mifflin-infinity", "--delete-branch"] in run.commands
    assert ["git", "-C", str(tmp_path), "push", "-q", "origin", "--delete", "fix/bulk-discount"] in run.commands
    assert not [c for c in run.commands if "main" in c and "--delete" in c]


def test_clear_dir_keeps_directory(tmp_path):
    (tmp_path / "a.pptx").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.json").write_text("y")
    assert reset_demo.clear_dir(tmp_path) == 2
    assert tmp_path.is_dir() and list(tmp_path.iterdir()) == []


def test_clear_dir_missing_is_fine(tmp_path):
    assert reset_demo.clear_dir(tmp_path / "nope") == 0
