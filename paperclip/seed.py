"""Create (or refresh) Dunder Mifflin Scranton in a local Paperclip instance.

Usage: paperclip/.venv/bin/python paperclip/seed.py
Env:   PAPERCLIP_URL (default http://127.0.0.1:3100), DEMO_REPO, ARTIFACTS_DIR, GATEWAY_PUBLIC_URL

Idempotent: the company, goal, agents and issues are matched by name/title and
reused. Existing agents get their instructions refreshed; existing issues are
left alone. Seed issues are never assigned, so seeding wakes no agent; their
owner is recorded in a description footer instead. Writes the id mapping to
backend/company/data/paperclip_ids.json.
"""

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

import httpx
import yaml

PAPERCLIP_DIR = Path(__file__).resolve().parent
REPO_ROOT = PAPERCLIP_DIR.parent
DEFAULT_IDS_PATH = REPO_ROOT / "backend" / "company" / "data" / "paperclip_ids.json"

COMPANY_NAME = "Dunder Mifflin Paper Company — Scranton"
COMPANY_DESCRIPTION = "Paper and office supplies for northeastern Pennsylvania. Home of Dunder Mifflin Infinity."
GOAL_TITLE = "Beat Stamford in Q4"
# Managers before their reports, so reportsTo ids exist when each agent is created.
ROLE_ORDER = ("ceo", "cfo", "eng_lead", "sales_lead", "engineer")
# Paperclip's fixed role categories (paperclip-findings.md); the title carries the real job.
PAPERCLIP_ROLE = {"ceo": "ceo", "cfo": "cfo", "eng_lead": "cto", "engineer": "engineer", "sales_lead": "general"}


def render(template: str, values: dict[str, str]) -> str:
    """Fill {UPPER_CASE} placeholders; raises KeyError on one with no value."""
    return re.sub(r"\{([A-Z_]+)\}", lambda m: values[m.group(1)], template)


def seed_footer(owner_role: str) -> str:
    return f"\n\n---\norigin: seed\nowner: {owner_role}"


def _json(resp: httpx.Response):
    resp.raise_for_status()
    return json.loads(resp.text, strict=False)  # Paperclip replies can contain raw control characters


def _items(data) -> list[dict]:
    return data if isinstance(data, list) else data.get("items") or data.get("data") or []


async def _get_or_create(client: httpx.AsyncClient, path: str, key: str, value: str, body: dict) -> tuple[dict, bool]:
    existing = next((x for x in _items(_json(await client.get(path))) if x.get(key) == value), None)
    if existing:
        return existing, False
    return _json(await client.post(path, json=body)), True


async def _refresh_instructions(client: httpx.AsyncClient, agent_id: str, content: str) -> None:
    """Overwrite AGENTS.md if it changed. PATCH on the agent rejects instructionsBundle; this endpoint
    needs the current revision id as baseRevisionId (optimistic locking)."""
    path = f"/api/agents/{agent_id}/instructions-bundle/file"
    current = _json(await client.get(path, params={"path": "AGENTS.md"}))
    if current["contentHash"] == hashlib.sha256(content.encode()).hexdigest():
        return
    _json(await client.put(path, json={"path": "AGENTS.md", "content": content,
                                       "baseRevisionId": current["revision"]["id"]}))


def _load_roles(repo_root: Path) -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in (repo_root / "backend" / "roles").glob("*.yaml")}


async def seed(client: httpx.AsyncClient, *, repo_root: Path, demo_repo: Path, artifacts_dir: Path,
               gateway_url: str, ids_path: Path = DEFAULT_IDS_PATH) -> dict:
    roles = _load_roles(repo_root)
    placeholders = {
        "ARTIFACTS_DIR": str(artifacts_dir),
        "GATEWAY_PUBLIC_URL": gateway_url.rstrip("/"),
        "SKILLS_DIR": str(repo_root / "paperclip" / "skills"),
        "PYTHON": str(repo_root / "paperclip" / ".venv" / "bin" / "python"),
        "DEMO_REPO": str(demo_repo),
        "COMPANY_DATA_DIR": str(repo_root / "backend" / "company" / "data"),
    }

    company, _ = await _get_or_create(client, "/api/companies", "name", COMPANY_NAME,
                                      {"name": COMPANY_NAME, "description": COMPANY_DESCRIPTION})
    cid = company["id"]
    goal, _ = await _get_or_create(client, f"/api/companies/{cid}/goals", "title", GOAL_TITLE,
                                   {"title": GOAL_TITLE, "level": "company", "status": "active"})

    agent_ids: dict[str, str] = {}
    for role_id in ROLE_ORDER:
        role = roles[role_id]
        instructions = render((repo_root / "paperclip" / "agents" / role_id / "AGENTS.md").read_text(), placeholders)
        bundle = {"files": {"AGENTS.md": instructions}}
        body = {
            "name": role["name"],
            "role": PAPERCLIP_ROLE[role_id],
            "title": role["title"],
            "adapterType": "claude_local",
            "adapterConfig": {"cwd": str(demo_repo if role_id == "engineer" else repo_root)},
            "instructionsBundle": bundle,
        }
        if role["reports_to"]:
            body["reportsTo"] = agent_ids[role["reports_to"]]
        agent, created = await _get_or_create(client, f"/api/companies/{cid}/agents", "name", role["name"], body)
        if not created:
            refresh = {"title": role["title"]}
            if role["reports_to"]:
                refresh["reportsTo"] = agent_ids[role["reports_to"]]
            _json(await client.patch(f"/api/agents/{agent['id']}", json=refresh))
            await _refresh_instructions(client, agent["id"], instructions)
        # New agents start paused and usually auto-ready within seconds; 409 means it's already running.
        resumed = await client.post(f"/api/agents/{agent['id']}/resume", json={})
        if resumed.status_code != 409:
            _json(resumed)
        agent_ids[role_id] = agent["id"]

    existing_issues = {i["title"]: i for i in _items(_json(await client.get(f"/api/companies/{cid}/issues")))}
    names = {r: roles[r]["name"] for r in roles}
    issue_ids: dict[str, str] = {}
    for raw in json.loads((repo_root / "backend" / "company" / "data" / "issues_seed.json").read_text()):
        issue = existing_issues.get(raw["title"])
        if issue is None:
            issue = _json(await client.post(f"/api/companies/{cid}/issues", json={
                "title": raw["title"],
                "description": raw["description"] + seed_footer(raw["assignee_role"]),
                # Paperclip refuses in_progress without an assignee, and assigning would wake the agent.
                "status": "todo" if raw["status"] == "in_progress" else raw["status"],
                "priority": "critical" if raw["flagged"] else "medium",
            }))
            for comment in raw.get("comments", []):
                author = names.get(comment["author_role"], "Board")
                _json(await client.post(f"/api/issues/{issue['id']}/comments",
                                        json={"body": f"{author}: {comment['body']}"}))
        issue_ids[raw["task_id"]] = issue["id"]

    ids = {"company_id": cid, "goal_id": goal["id"], "agents": agent_ids, "issues": issue_ids}
    ids_path.write_text(json.dumps(ids, indent=2) + "\n")
    return ids


async def main() -> None:
    artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", REPO_ROOT / "artifacts")).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    demo_repo = Path(os.getenv("DEMO_REPO", REPO_ROOT.parent / "dunder-mifflin-infinity")).resolve()
    async with httpx.AsyncClient(base_url=os.getenv("PAPERCLIP_URL", "http://127.0.0.1:3100"), timeout=30) as client:
        ids = await seed(client, repo_root=REPO_ROOT, demo_repo=demo_repo, artifacts_dir=artifacts_dir,
                         gateway_url=os.getenv("GATEWAY_PUBLIC_URL", "http://localhost:8000"))
    print(f"Seeded company {ids['company_id']}: {len(ids['agents'])} agents, {len(ids['issues'])} issues")
    print(f"Ids written to {DEFAULT_IDS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
