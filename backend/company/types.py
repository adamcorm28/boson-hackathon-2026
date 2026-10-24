"""Shared contract between the voice gateway and the company layer.

See docs/superpowers/plans/2026-10-23-voice-company-index.md (shared contract 1).
Change a signature here only after telling the voice gateway owner.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

Status = Literal["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"]
STATUSES: tuple[Status, ...] = ("backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled")

ROLE_IDS = ("ceo", "cfo", "eng_lead", "engineer", "sales_lead")
VOICE_TOOL_NAMES = frozenset({
    "get_company_overview", "read_inbox", "read_email", "get_board", "get_issue",
    "get_my_work", "delegate_task", "get_financials", "get_ai_spend",
    "get_pipeline", "get_deal", "lookup_company", "web_search",
})


@dataclass
class Comment:
    author_role: str | None
    body: str
    created_at: str  # ISO 8601


@dataclass
class Artifact:
    kind: Literal["pr", "diff", "pptx", "xlsx", "link"]
    url: str
    label: str


@dataclass
class Issue:
    task_id: str
    title: str
    status: Status
    assignee_role: str | None
    origin: Literal["voice", "seed"]
    requested_by_role: str | None
    flagged: bool
    description: str
    comments: list[Comment] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class TaskResult:
    task_id: str
    title: str
    from_role: str
    requested_by_role: str | None
    summary: str
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass
class AgentStatus:
    role: str
    state: Literal["idle", "working"]
    current_task_id: str | None
    last_comment: str | None


class CompanyUnavailable(Exception):
    """The company backend is unreachable or timed out (3 s)."""


class CompanyAPI(Protocol):
    async def list_issues(self, role: str | None = None, status: Status | None = None) -> list[Issue]: ...

    async def get_issue(self, task_id: str) -> Issue:
        """Raises KeyError if the task id is unknown."""
        ...

    async def create_task(self, assignee_role: str, title: str, brief: str, requested_by_role: str) -> str: ...

    async def add_comment(self, task_id: str, body: str) -> None: ...

    async def get_agent_status(self, role: str) -> AgentStatus: ...

    async def get_costs(self) -> dict:
        """{"total_cents": int, "by_role": {role: int}}"""
        ...
