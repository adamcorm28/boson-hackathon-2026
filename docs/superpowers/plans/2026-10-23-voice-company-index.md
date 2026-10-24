# Voice Company: build plan index

**Spec:** `docs/superpowers/specs/2026-10-23-voice-company-design.md` (read it first, especially §5, §6 and §7a)

There are three plans, one per person. They can run in parallel because everything between them goes through the contracts on this page.

| Plan | Owner | File |
|---|---|---|
| A. Voice gateway | voice person | `2026-10-23-voice-gateway.md` |
| B. Company layer + Paperclip | Thomas (his laptop runs Paperclip and Claude Code) | `2026-10-23-company-paperclip.md` |
| C. Arcade frontend | frontend person | `2026-10-23-arcade-frontend.md` |

## Timeline (Fri 2026-10-23 → Sat 2026-10-24)

| When | A | B | C |
|---|---|---|---|
| First hour | A1 spike (voices + injection) | **B1 first, push within 45 min** (A and C depend on it), then B4 spike | C1–C2 against mocks |
| ~1:00 AM | **Checkpoint 1:** a real voice call in the arcade with the mock company (A7 + C4) | | |
| Overnight | A2–A8 | B2–B9 | C3–C7 |
| ~8:00 AM | **Checkpoint 2:** `COMPANY_BACKEND=paperclip`, then delegate → Dwight fixes → ping inside Jim's call (A9 + B10 + C8) | | |
| 11:00 AM | **Feature freeze.** Rehearse the §8 storyline | | |
| ~1:30 PM | **Record.** Reset the demo between takes (B10 reset script) | | |

## Ports and env (all plans)

- Gateway: `http://localhost:8000`. Paperclip: `http://localhost:3100`. Vite: `http://localhost:5173`.
- `backend/.env` holds:
  - `BOSON_API_KEY`, `ANTHROPIC_API_KEY`
  - `COMPANY_BACKEND=mock|paperclip` (default `mock`)
  - `PAPERCLIP_URL=http://localhost:3100`
  - `INJECTION_MODE=function_call|user_message` (set from A1 findings)
  - `ARTIFACTS_DIR` (default `<repo>/artifacts`)
  - `GATEWAY_PUBLIC_URL=http://localhost:8000`
- Backend tests: `cd backend && pytest`. Frontend tests: `cd frontend && npx vitest run`.

## Shared contract 1: Python company layer (`backend/company/types.py`, created in B1)

```python
Status = Literal["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"]
ROLE_IDS = ("ceo", "cfo", "eng_lead", "engineer", "sales_lead")
VOICE_TOOL_NAMES = frozenset({
    "get_company_overview", "read_inbox", "read_email", "get_board", "get_issue",
    "get_my_work", "delegate_task", "get_financials", "get_ai_spend",
    "get_pipeline", "get_deal", "lookup_company", "web_search",
})

@dataclass
class Comment:   author_role: str | None; body: str; created_at: str          # ISO 8601
@dataclass
class Artifact:  kind: Literal["pr", "diff", "pptx", "xlsx", "link"]; url: str; label: str
@dataclass
class Issue:     task_id: str; title: str; status: Status; assignee_role: str | None
                 origin: Literal["voice", "seed"]; requested_by_role: str | None
                 flagged: bool; description: str; comments: list[Comment]; updated_at: str
@dataclass
class TaskResult: task_id: str; title: str; from_role: str; requested_by_role: str | None
                  summary: str; artifacts: list[Artifact]
@dataclass
class AgentStatus: role: str; state: Literal["idle", "working"]
                   current_task_id: str | None; last_comment: str | None

class CompanyUnavailable(Exception): ...   # backend unreachable or timed out (3 s)

class CompanyAPI(Protocol):
    async def list_issues(self, role: str | None = None, status: Status | None = None) -> list[Issue]: ...
    async def get_issue(self, task_id: str) -> Issue: ...                       # raises KeyError if unknown
    async def create_task(self, assignee_role: str, title: str, brief: str, requested_by_role: str) -> str: ...
    async def add_comment(self, task_id: str, body: str) -> None: ...
    async def get_agent_status(self, role: str) -> AgentStatus: ...
    async def get_costs(self) -> dict: ...                                       # {"total_cents": int, "by_role": {role: int}}

def get_company() -> CompanyAPI   # backend/company/__init__.py; picks mock or paperclip from COMPANY_BACKEND
```

`backend/company/data_tools.py` has synchronous pure functions that return JSON-safe dicts and lists:
- `company_overview() -> dict`
- `get_pipeline() -> list[dict]`
- `get_deal(name: str) -> dict | None`
- `get_financials() -> dict`
- `read_inbox() -> list[dict]`
- `read_email(email_id: str) -> dict | None`
- `lookup_company(topic: str) -> dict`

`backend/company/watcher.py`:
- `TaskWatcher(company: CompanyAPI, on_update: Callable[[Issue], Awaitable[None]], on_complete: Callable[[TaskResult], Awaitable[None]], interval: float = 3.0)`
- Methods: `start()` and `stop()`, both async, and `poll_once()`.

**RESULT convention.** Work-body agents end every voice task with one comment in this form:
```
RESULT: <2–4 sentence summary>
ARTIFACT: <kind> <url> <label>      # zero or more lines
```
A task is complete when its status is `in_review` or `done` **and** it has a comment starting with `RESULT:`.

## Shared contract 2: HTTP/WS between gateway and frontend

This is exactly spec §7a, with these additions:
- SSE frames are `event: <type>\ndata: <json>\n\n`.
- A `ping` is emitted with `to_role` = the active call's role when a result is injected into a call, and with `to_role: null` when no call was active.
- The frontend marks "!" on `from_role` after `task.completed`, and clears it when that task's result is opened or that role is called.
- A second `WS /call/*` while one call is active is closed with code `4409`.
- Artifacts are served at `GET /artifacts/<filename>`.

TypeScript mirror: `frontend/src/api/types.ts` (created in C1).
