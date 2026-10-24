"""In-memory CompanyAPI seeded from data/issues_seed.json.

Lets the voice gateway and frontend run before Paperclip is up. The extra
hooks `set_status` and `complete` let tests and demos fake agent progress.
"""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from company.types import AgentStatus, Artifact, Comment, Issue, Status

SEED_PATH = Path(__file__).parent / "data" / "issues_seed.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class MockCompany:
    def __init__(self, seed_path: Path = SEED_PATH):
        self._issues: dict[str, Issue] = {}
        for raw in json.loads(seed_path.read_text()):
            comments = [Comment(**c) for c in raw.pop("comments", [])]
            self._issues[raw["task_id"]] = Issue(
                origin="seed", requested_by_role=None, comments=comments, updated_at=_now(), **raw
            )
        self._next_id = max(int(tid.split("-")[1]) for tid in self._issues) + 1

    # --- CompanyAPI -------------------------------------------------------

    async def list_issues(self, role: str | None = None, status: Status | None = None) -> list[Issue]:
        return [
            copy.deepcopy(i)
            for i in self._issues.values()
            if (role is None or i.assignee_role == role) and (status is None or i.status == status)
        ]

    async def get_issue(self, task_id: str) -> Issue:
        return copy.deepcopy(self._issues[task_id])

    async def create_task(self, assignee_role: str, title: str, brief: str, requested_by_role: str) -> str:
        task_id = f"DM-{self._next_id}"
        self._next_id += 1
        self._issues[task_id] = Issue(
            task_id=task_id,
            title=title,
            status="todo",
            assignee_role=assignee_role,
            origin="voice",
            requested_by_role=requested_by_role,
            flagged=False,
            description=brief,
            updated_at=_now(),
        )
        return task_id

    async def add_comment(self, task_id: str, body: str) -> None:
        self._comment(task_id, None, body)

    async def get_agent_status(self, role: str) -> AgentStatus:
        working = [i for i in self._issues.values() if i.assignee_role == role and i.status == "in_progress"]
        if not working:
            return AgentStatus(role=role, state="idle", current_task_id=None, last_comment=None)
        current = working[-1]
        last = current.comments[-1].body[:300] if current.comments else None
        return AgentStatus(role=role, state="working", current_task_id=current.task_id, last_comment=last)

    async def get_costs(self) -> dict:
        return {
            "total_cents": 412,
            "by_role": {"ceo": 38, "cfo": 54, "eng_lead": 61, "engineer": 187, "sales_lead": 72},
        }

    # --- test / demo hooks ------------------------------------------------

    def set_status(self, task_id: str, status: Status) -> None:
        issue = self._issues[task_id]
        issue.status = status
        issue.updated_at = _now()

    def complete(self, task_id: str, summary: str, artifacts: tuple[Artifact, ...] = ()) -> None:
        """Simulate the assignee finishing: RESULT comment, then status done."""
        lines = [f"RESULT: {summary}"] + [f"ARTIFACT: {a.kind} {a.url} {a.label}" for a in artifacts]
        self._comment(task_id, self._issues[task_id].assignee_role, "\n".join(lines))
        self.set_status(task_id, "done")

    def fail(self, task_id: str, reason: str, touch: bool = True) -> None:
        """Simulate the assignee's run failing. Paperclip doesn't touch the issue then (touch=False)."""
        issue = self._issues[task_id]
        issue.failed_reason = reason
        if touch:
            issue.updated_at = _now()

    def _comment(self, task_id: str, author_role: str | None, body: str) -> None:
        issue = self._issues[task_id]
        issue.comments.append(Comment(author_role=author_role, body=body, created_at=_now()))
        issue.updated_at = _now()
