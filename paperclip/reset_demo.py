"""Reset everything a demo take changes, so the next take starts from the seeded bug.

Usage: paperclip/.venv/bin/python paperclip/reset_demo.py [--skip-github]
       (or: make reset-demo)

1. Paperclip: cancel active agent runs, cancel voice-created tasks, put seed issues back to their
   seeded status and comments, and reset every agent's Claude Code session (otherwise agents
   resume the previous take's conversation, e.g. Dwight remembers the fix).
2. Demo repo: back to main at the seeded-bug tag, local fix/* branches deleted.
3. GitHub: close open PRs and delete remote fix/* branches.
4. Empty artifacts/ and backend/data/calls/, then re-run the seed.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

import seed

TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled", "canceled", "timed_out", "error", "skipped"}
DEMO_REPO_SLUG = os.getenv("DEMO_REPO_SLUG", "thomas-m1/dunder-mifflin-infinity")


async def reset_paperclip(client: httpx.AsyncClient, *, repo_root: Path) -> dict:
    summary = {"company_found": False, "runs_cancelled": 0, "voice_tasks_cancelled": 0,
               "seed_issues_restored": 0, "comments_deleted": 0, "sessions_reset": 0}
    companies = seed._items(seed._json(await client.get("/api/companies")))
    company = next((c for c in companies if c.get("name") == seed.COMPANY_NAME), None)
    if company is None:
        return summary
    summary["company_found"] = True
    cid = company["id"]

    # Stop agents first so nothing writes while we clean up.
    for run in seed._items(seed._json(await client.get(f"/api/companies/{cid}/heartbeat-runs"))):
        if run.get("status") not in TERMINAL_RUN_STATUSES:
            resp = await client.post(f"/api/heartbeat-runs/{run['id']}/cancel", json={})
            if resp.is_success:
                summary["runs_cancelled"] += 1

    names = {role_id: role["name"] for role_id, role in seed._load_roles(repo_root).items()}
    seeded = {raw["title"]: raw for raw in json.loads((repo_root / "backend/company/data/issues_seed.json").read_text())}
    for issue in seed._items(seed._json(await client.get(f"/api/companies/{cid}/issues"))):
        if "\norigin: voice" in (issue.get("description") or ""):
            if issue["status"] != "cancelled":
                seed._json(await client.patch(f"/api/issues/{issue['id']}", json={"status": "cancelled"}))
                summary["voice_tasks_cancelled"] += 1
        elif raw := seeded.get(issue["title"]):
            expected_status = "todo" if raw["status"] == "in_progress" else raw["status"]
            if issue["status"] != expected_status:
                seed._json(await client.patch(f"/api/issues/{issue['id']}", json={"status": expected_status}))
                summary["seed_issues_restored"] += 1
            expected = {f"{names.get(c['author_role'], 'Board')}: {c['body']}" for c in raw.get("comments", [])}
            for comment in seed._json(await client.get(f"/api/issues/{issue['id']}/comments")):
                if comment["body"] not in expected:
                    seed._json(await client.delete(f"/api/issues/{issue['id']}/comments/{comment['id']}"))
                    summary["comments_deleted"] += 1

    for agent in seed._items(seed._json(await client.get(f"/api/companies/{cid}/agents"))):
        seed._json(await client.post(f"/api/agents/{agent['id']}/runtime-state/reset-session", json={}))
        summary["sessions_reset"] += 1
    return summary


def _git(repo: Path, *args: str) -> list[str]:
    return ["git", "-C", str(repo), *args]


def reset_repo(repo: Path, run=subprocess.run) -> None:
    run(_git(repo, "checkout", "-q", "-f", "main"), check=True)
    run(_git(repo, "reset", "-q", "--hard", "seeded-bug"), check=True)
    listed = run(_git(repo, "branch", "--list", "fix/*"), capture_output=True, text=True, check=True).stdout
    branches = [line.strip().lstrip("* ") for line in listed.splitlines() if line.strip().lstrip("* ").startswith("fix/")]
    if branches:
        run(_git(repo, "branch", "-D", *branches), check=True)


def reset_github(repo: Path, slug: str, run=subprocess.run) -> None:
    prs = run(["gh", "pr", "list", "--repo", slug, "--state", "open", "--json", "number"],
              capture_output=True, text=True, check=False)
    if prs.returncode != 0:
        print(f"  skipping GitHub PRs: {prs.stderr.strip() or 'gh failed'}")
    else:
        for pr in json.loads(prs.stdout or "[]"):
            run(["gh", "pr", "close", str(pr["number"]), "--repo", slug, "--delete-branch"], check=False)
    heads = run(_git(repo, "ls-remote", "--heads", "origin", "fix/*"), capture_output=True, text=True, check=False).stdout
    for line in heads.splitlines():
        ref = line.split("\t")[-1]
        if ref.startswith("refs/heads/fix/"):
            run(_git(repo, "push", "-q", "origin", "--delete", ref.removeprefix("refs/heads/")), check=False)


def clear_dir(path: Path) -> int:
    """Delete everything inside `path`, keeping the directory. Returns how many entries were removed."""
    if not path.is_dir():
        return 0
    entries = list(path.iterdir())
    for entry in entries:
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    return len(entries)


async def main(skip_github: bool) -> None:
    repo_root = seed.REPO_ROOT
    demo_repo = Path(os.getenv("DEMO_REPO", repo_root.parent / "dunder-mifflin-infinity")).resolve()
    artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", repo_root / "artifacts")).resolve()
    paperclip_url = os.getenv("PAPERCLIP_URL", "http://127.0.0.1:3100")

    async with httpx.AsyncClient(base_url=paperclip_url, timeout=30) as client:
        print("Paperclip:", await reset_paperclip(client, repo_root=repo_root))
        print("Demo repo:", demo_repo)
        reset_repo(demo_repo)
        if not skip_github and shutil.which("gh"):
            reset_github(demo_repo, DEMO_REPO_SLUG)
            print("GitHub: open PRs closed, remote fix/* branches deleted")
        print(f"Cleared {clear_dir(artifacts_dir)} artifact(s), {clear_dir(repo_root / 'backend/data/calls')} call log(s)")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ids = await seed.seed(client, repo_root=repo_root, demo_repo=demo_repo, artifacts_dir=artifacts_dir,
                              gateway_url=os.getenv("GATEWAY_PUBLIC_URL", "http://localhost:8000"))
        print(f"Re-seeded: {len(ids['agents'])} agents, {len(ids['issues'])} issues. Ready for the next take.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with git/gh output
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-github", action="store_true", help="don't touch PRs or remote branches")
    asyncio.run(main(parser.parse_args().skip_github))
