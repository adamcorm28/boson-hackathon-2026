"""Process-wide gateway singletons. Routes read these at request time, so tests can swap them."""

import logging
import os
from pathlib import Path

from company import get_company
from company.types import CompanyAPI, CompanyUnavailable, Issue, TaskResult
from gateway import company_compat, upstream
from gateway.events import EventBus
from gateway.injector import NotificationQueue
from gateway.memory import CallMemory
from gateway.roles import Role, load_roles
from gateway.simulator import WorkSimulator

log = logging.getLogger(__name__)

REPO_DIR = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", REPO_DIR / "artifacts"))
PUBLIC_URL = os.getenv("GATEWAY_PUBLIC_URL", "http://localhost:8000")

bus: EventBus = EventBus()
roles: dict[str, Role] = load_roles()
company: CompanyAPI = get_company()
queue: NotificationQueue = NotificationQueue()
memory: CallMemory = CallMemory()
injection_mode: str = os.getenv("INJECTION_MODE", "user_message")
connect_upstream = upstream.connect_boson
active_call = None  # CallSession | None, set by the WS route
watcher = None  # company.watcher.TaskWatcher once B9 lands
simulator: WorkSimulator | None = None  # fake work bodies, mock company + SIMULATE_WORK_SECONDS only


def _name(role_id: str | None) -> str:
    return roles[role_id].name if role_id in roles else (role_id or "Someone")


async def on_update(issue: Issue) -> None:
    bus.publish("task.updated", {
        "task_id": issue.task_id, "status": issue.status,
        "assignee_role": issue.assignee_role, "title": issue.title,
    })
    role = issue.assignee_role
    if role is None or (active_call is not None and active_call.role.id == role):
        return  # an agent on a call stays "on_call"
    try:
        status = await company.get_agent_status(role)
        state = status.state
    except CompanyUnavailable:
        state = "working" if issue.status == "in_progress" else "idle"
    bus.publish("agent.status", {"role": role, "state": state})


async def on_complete(result: TaskResult) -> None:
    bus.publish("task.completed", {
        "task_id": result.task_id, "from_role": result.from_role,
        "title": result.title, "summary": result.summary,
    })
    # The active call announces it in a quiet gap (and pings then); otherwise the
    # next call's briefing delivers it and the frontend rings the sender's phone.
    queue.push(result)
    if active_call is None:
        bus.publish("ping", {
            "to_role": None, "from_role": result.from_role, "task_id": result.task_id,
            "text": f"{_name(result.from_role)}: {result.title} is done",
        })


async def startup() -> None:
    global watcher, simulator
    watcher = company_compat.make_watcher(company, on_update, on_complete)
    if watcher is not None:
        await watcher.start()
    seconds = float(os.getenv("SIMULATE_WORK_SECONDS", "0") or 0)
    if seconds > 0:
        if not hasattr(company, "complete"):
            log.warning("SIMULATE_WORK_SECONDS ignored: only works with COMPANY_BACKEND=mock")
        else:
            simulator = WorkSimulator(
                company, roles, bus, on_update, on_complete, work_seconds=seconds,
                artifacts_dir=ARTIFACTS_DIR, public_url=PUBLIC_URL,
                announce_directly=lambda: watcher is None,
            )
            await simulator.start()


async def shutdown() -> None:
    if simulator is not None:
        await simulator.stop()
    if watcher is not None:
        await watcher.stop()
