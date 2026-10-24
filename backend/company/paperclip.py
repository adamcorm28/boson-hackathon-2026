"""CompanyAPI backed by a local Paperclip instance (routes: docs/superpowers/spikes/paperclip-findings.md).

Ids come from backend/company/data/paperclip_ids.json (written by paperclip/seed.py) or, when that
file is missing, are discovered on first use by matching the company, agent and seed issue names
against the seeded Paperclip data. Mapping rules:
- roles <-> agent ids via ids["agents"]
- origin and ownership live in a description footer ("---" then "key: value" lines): voice tasks carry
  origin/requested_by and are assigned; seed issues carry origin/owner and stay unassigned (assigning wakes agents)
- seed issues keep their seed id (DM-101) as task_id; voice tasks use the Paperclip identifier (DUNA-11)
"""

import json
import os
import re
from pathlib import Path

import httpx
import yaml

from company.types import AgentStatus, Comment, CompanyUnavailable, Issue, Status

DATA_DIR = Path(__file__).parent / "data"
ROLES_DIR = Path(__file__).parent.parent / "roles"
DEFAULT_IDS_PATH = DATA_DIR / "paperclip_ids.json"
COMPANY_NAME = "Dunder Mifflin Paper Company — Scranton"  # must match paperclip/seed.py
TIMEOUT_SECONDS = 3.0
FLAGGED_PRIORITIES = ("critical", "high")
LAST_COMMENT_CHARS = 300
FAILED_RUN_STATUSES = ("failed", "timed_out", "error")
SETTLED_STATUSES = ("in_review", "done", "cancelled")
# Anthropic API list prices, USD per million tokens: (input, cache hits, output).
# From platform.claude.com/docs/en/about-claude/pricing, checked 2026-10-24.
PRICES_PER_MTOK = {
    "claude-opus-5": (5.00, 0.50, 25.00),
    "claude-opus-5-5": (4.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 0.10, 10.00),
    "claude-fable-5-1": (10.00, 0.25, 50.00),
}
DEFAULT_PRICING_MODEL = "claude-opus-5"
# Research runs on a stronger model. Paperclip's bundled Claude Code can't run Opus 5.5, so research
# tasks override the adapter to the "cli" engine (the installed `claude`), which can.
DEFAULT_RESEARCH_MODEL = "claude-opus-5-5"  # what the agents run (see DEFAULT_AGENT_MODEL in paperclip/seed.py)
_FOOTER = re.compile(r"\n\n---\n((?:[a-z_]+: [^\n]*\n?)+)\s*$")


def _split_footer(description: str) -> tuple[str, dict[str, str]]:
    m = _FOOTER.search(description or "")
    if not m:
        return description or "", {}
    fields = dict(line.split(": ", 1) for line in m.group(1).strip().splitlines())
    return description[: m.start()], fields


class PaperclipCompany:
    def __init__(self, base_url: str, ids: dict | None = None, client: httpx.AsyncClient | None = None):
        self.base_url = base_url
        self.ids: dict | None = None  # None until loaded or discovered
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT_SECONDS)
        if ids is not None:
            self._use_ids(ids)

    @classmethod
    def from_env(cls, ids_path: Path | None = None) -> "PaperclipCompany":
        ids_path = ids_path or DEFAULT_IDS_PATH
        ids = json.loads(ids_path.read_text()) if ids_path.exists() else None
        return cls(os.getenv("PAPERCLIP_URL", "http://127.0.0.1:3100"), ids)

    def _use_ids(self, ids: dict) -> None:
        self.ids = ids
        self._role_by_agent = {agent_id: role for role, agent_id in ids["agents"].items()}
        self._seed_id_by_issue = {issue_id: seed_id for seed_id, issue_id in ids["issues"].items()}

    async def _ensure_ids(self) -> None:
        if self.ids is None:
            self._use_ids(await self._discover_ids())

    async def _discover_ids(self) -> dict:
        """Find the seeded company, agents and seed issues by name, as paperclip/seed.py created them."""
        company = next((c for c in await self._request("GET", "/api/companies") if c.get("name") == COMPANY_NAME), None)
        if company is None:
            raise CompanyUnavailable(f"{COMPANY_NAME!r} isn't in Paperclip yet; run paperclip/seed.py")
        cid = company["id"]
        role_by_name = {r["name"]: r["id"] for r in (yaml.safe_load(p.read_text()) for p in ROLES_DIR.glob("*.yaml"))}
        agents = {role_by_name[a["name"]]: a["id"]
                  for a in await self._request("GET", f"/api/companies/{cid}/agents") if a.get("name") in role_by_name}
        seed_id_by_title = {i["title"]: i["task_id"] for i in json.loads((DATA_DIR / "issues_seed.json").read_text())}
        issues = {seed_id_by_title[i["title"]]: i["id"]
                  for i in await self._request("GET", f"/api/companies/{cid}/issues") if i.get("title") in seed_id_by_title}
        return {"company_id": cid, "agents": agents, "issues": issues}

    # --- HTTP ---------------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs):
        try:
            resp = await self._client.request(method, path, timeout=TIMEOUT_SECONDS, **kwargs)
        except httpx.TransportError as e:
            raise CompanyUnavailable(f"Paperclip unreachable: {e}") from e
        if resp.status_code == 404:
            raise KeyError(path)
        if resp.is_error:
            raise CompanyUnavailable(f"Paperclip {method} {path} failed: {resp.status_code} {resp.text[:200]}")
        return json.loads(resp.text, strict=False) if resp.text else None  # replies can hold raw control chars

    def _paperclip_id(self, task_id: str) -> str:
        return self.ids["issues"].get(task_id, task_id)  # seed id -> uuid; identifiers like DUNA-11 work as-is

    # --- mapping ------------------------------------------------------------------------

    def _issue(self, raw: dict, comments: list[Comment] | None = None) -> Issue:
        description, footer = _split_footer(raw.get("description") or "")
        assignee = self._role_by_agent.get(raw.get("assigneeAgentId")) or footer.get("owner")
        return Issue(
            task_id=self._seed_id_by_issue.get(raw["id"], raw["identifier"]),
            title=raw["title"],
            status=raw["status"],
            assignee_role=assignee,
            origin="voice" if footer.get("origin") == "voice" else "seed",
            requested_by_role=footer.get("requested_by"),
            flagged=raw.get("priority") in FLAGGED_PRIORITIES,
            description=description,
            comments=comments or [],
            updated_at=raw.get("updatedAt", ""),
            kind="research" if footer.get("kind") == "research" else "task",
        )

    def _comment(self, raw: dict) -> Comment:
        return Comment(author_role=self._role_by_agent.get(raw.get("authorAgentId")), body=raw["body"],
                       created_at=raw.get("createdAt", ""))

    async def _comments(self, task_id: str) -> list[Comment]:
        raw = await self._request("GET", f"/api/issues/{self._paperclip_id(task_id)}/comments")
        return [self._comment(c) for c in raw]

    # --- CompanyAPI ---------------------------------------------------------------------

    async def list_issues(self, role: str | None = None, status: Status | None = None) -> list[Issue]:
        await self._ensure_ids()
        raw = await self._request("GET", f"/api/companies/{self.ids['company_id']}/issues")
        issues = [self._issue(r) for r in raw]  # the API has no filters; filter here
        return [i for i in issues if (role is None or i.assignee_role == role) and (status is None or i.status == status)]

    async def get_issue(self, task_id: str) -> Issue:
        await self._ensure_ids()
        try:
            raw = await self._request("GET", f"/api/issues/{self._paperclip_id(task_id)}")
        except KeyError:
            raise KeyError(task_id) from None
        issue = self._issue(raw, await self._comments(task_id))
        if issue.origin == "voice" and issue.status not in SETTLED_STATUSES:
            issue.failed_reason = await self._failed_run_reason(task_id)
        return issue

    async def _failed_run_reason(self, task_id: str) -> str | None:
        """Why the latest run failed, unless a retry is scheduled. None if it's fine or still running."""
        try:
            runs = await self._request("GET", f"/api/issues/{self._paperclip_id(task_id)}/runs")
        except KeyError:
            return None
        if not runs:
            return None
        latest = max(runs, key=lambda r: r.get("startedAt") or "")
        if latest.get("status") not in FAILED_RUN_STATUSES or latest.get("scheduledRetryAt"):
            return None
        return latest.get("errorCode") or latest.get("error") or latest["status"]

    async def create_task(self, assignee_role: str, title: str, brief: str, requested_by_role: str,
                          kind: str = "task") -> str:
        await self._ensure_ids()
        footer = f"\n\n---\norigin: voice\nrequested_by: {requested_by_role}" + ("\nkind: research" if kind == "research" else "")
        body = {
            "title": title,
            "description": brief + footer,
            "status": "todo",
            "assigneeAgentId": self.ids["agents"][assignee_role],  # assigning wakes the agent
        }
        if kind == "research":
            model = os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL)
            body["assigneeAdapterOverrides"] = {"adapterConfig": {"engine": "cli", "model": model}}
        raw = await self._request("POST", f"/api/companies/{self.ids['company_id']}/issues", json=body)
        return raw["identifier"]

    async def add_comment(self, task_id: str, body: str) -> None:
        await self._ensure_ids()
        await self._request("POST", f"/api/issues/{self._paperclip_id(task_id)}/comments", json={"body": body})

    async def get_agent_status(self, role: str) -> AgentStatus:
        working = await self.list_issues(role=role, status="in_progress")
        if not working:
            return AgentStatus(role=role, state="idle", current_task_id=None, last_comment=None)
        current = working[0]
        comments = await self._comments(current.task_id)
        last = comments[-1].body[:LAST_COMMENT_CHARS] if comments else None
        return AgentStatus(role=role, state="working", current_task_id=current.task_id, last_comment=last)

    async def get_costs(self) -> dict:
        """Billed cents per role, token counts, and what the same tokens would cost at API list prices.
        Runs on a Claude subscription bill 0 cents, so the estimate is the meaningful dollar figure.
        PAPERCLIP_PRICING_MODEL picks the price row; an unpriced model gives estimate=None."""
        await self._ensure_ids()
        rows = await self._request("GET", f"/api/companies/{self.ids['company_id']}/costs/by-agent")
        by_role, tokens = {}, {}
        for row in rows:
            role = self._role_by_agent.get(row.get("agentId"))
            if role is None:
                continue
            by_role[role] = int(row.get("costCents") or 0)
            tokens[role] = {"input": row.get("inputTokens", 0), "cached_input": row.get("cachedInputTokens", 0),
                            "output": row.get("outputTokens", 0)}
        return {
            "total_cents": sum(by_role.values()),
            "by_role": by_role,
            "tokens": {"by_role": tokens, "total": sum(sum(t.values()) for t in tokens.values())},
            "estimate": _list_price_estimate(tokens),
            "note": "Runs billed to the Claude subscription show 0 cents; the estimate prices the same tokens at API list prices.",
        }


def _list_price_estimate(tokens_by_role: dict[str, dict[str, int]]) -> dict | None:
    model = os.getenv("PAPERCLIP_PRICING_MODEL", DEFAULT_PRICING_MODEL)
    if model not in PRICES_PER_MTOK:
        return None
    input_price, cached_price, output_price = PRICES_PER_MTOK[model]

    def usd(t: dict[str, int]) -> float:
        return (t["input"] * input_price + t["cached_input"] * cached_price + t["output"] * output_price) / 1_000_000

    by_role = {role: round(usd(t), 4) for role, t in tokens_by_role.items()}
    return {
        "model": model,
        "by_role_usd": by_role,
        "total_usd": round(sum(usd(t) for t in tokens_by_role.values()), 4),
        "basis": f"{model} API list prices: ${input_price:.2f}/M input, ${cached_price:.2f}/M cached input, ${output_price:.2f}/M output",
    }
