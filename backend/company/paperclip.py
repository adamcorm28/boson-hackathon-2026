"""CompanyAPI backed by a local Paperclip instance (routes: docs/superpowers/spikes/paperclip-findings.md).

Needs backend/company/data/paperclip_ids.json, written by paperclip/seed.py. Mapping rules:
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

from company.types import AgentStatus, Comment, CompanyUnavailable, Issue, Status

DEFAULT_IDS_PATH = Path(__file__).parent / "data" / "paperclip_ids.json"
TIMEOUT_SECONDS = 3.0
FLAGGED_PRIORITIES = ("critical", "high")
LAST_COMMENT_CHARS = 300
# Anthropic API list prices, USD per million tokens: (input, cached input read, output).
# Only models whose cache-read price is published are listed (claude-api pricing table, 2026-10-06).
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 0.20, 10.00),
    "claude-fable-5-1": (10.00, 0.25, 50.00),
}
DEFAULT_PRICING_MODEL = "claude-opus-5-5"  # Claude Code's "opus" alias
_FOOTER = re.compile(r"\n\n---\n((?:[a-z_]+: [^\n]*\n?)+)\s*$")


def _split_footer(description: str) -> tuple[str, dict[str, str]]:
    m = _FOOTER.search(description or "")
    if not m:
        return description or "", {}
    fields = dict(line.split(": ", 1) for line in m.group(1).strip().splitlines())
    return description[: m.start()], fields


class PaperclipCompany:
    def __init__(self, base_url: str, ids: dict, client: httpx.AsyncClient | None = None):
        self.base_url = base_url
        self.ids = ids
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT_SECONDS)
        self._role_by_agent = {agent_id: role for role, agent_id in ids["agents"].items()}
        self._seed_id_by_issue = {issue_id: seed_id for seed_id, issue_id in ids["issues"].items()}

    @classmethod
    def from_env(cls, ids_path: Path | None = None) -> "PaperclipCompany":
        ids_path = ids_path or DEFAULT_IDS_PATH
        if not ids_path.exists():
            raise RuntimeError(f"{ids_path} not found; run paperclip/seed.py against Paperclip first")
        return cls(os.getenv("PAPERCLIP_URL", "http://127.0.0.1:3100"), json.loads(ids_path.read_text()))

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
        )

    def _comment(self, raw: dict) -> Comment:
        return Comment(author_role=self._role_by_agent.get(raw.get("authorAgentId")), body=raw["body"],
                       created_at=raw.get("createdAt", ""))

    async def _comments(self, task_id: str) -> list[Comment]:
        raw = await self._request("GET", f"/api/issues/{self._paperclip_id(task_id)}/comments")
        return [self._comment(c) for c in raw]

    # --- CompanyAPI ---------------------------------------------------------------------

    async def list_issues(self, role: str | None = None, status: Status | None = None) -> list[Issue]:
        raw = await self._request("GET", f"/api/companies/{self.ids['company_id']}/issues")
        issues = [self._issue(r) for r in raw]  # the API has no filters; filter here
        return [i for i in issues if (role is None or i.assignee_role == role) and (status is None or i.status == status)]

    async def get_issue(self, task_id: str) -> Issue:
        try:
            raw = await self._request("GET", f"/api/issues/{self._paperclip_id(task_id)}")
        except KeyError:
            raise KeyError(task_id) from None
        return self._issue(raw, await self._comments(task_id))

    async def create_task(self, assignee_role: str, title: str, brief: str, requested_by_role: str) -> str:
        raw = await self._request("POST", f"/api/companies/{self.ids['company_id']}/issues", json={
            "title": title,
            "description": f"{brief}\n\n---\norigin: voice\nrequested_by: {requested_by_role}",
            "status": "todo",
            "assigneeAgentId": self.ids["agents"][assignee_role],  # assigning wakes the agent
        })
        return raw["identifier"]

    async def add_comment(self, task_id: str, body: str) -> None:
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
