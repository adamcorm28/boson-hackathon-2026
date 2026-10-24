"""Fake work bodies for rehearsing without Paperclip (mock company only).

Enabled with SIMULATE_WORK_SECONDS=<n>. When a voice agent delegates a task, the
assignee "starts" after a few seconds (status in_progress plus a progress note),
then "finishes" after n seconds with a RESULT comment and a placeholder artifact,
which is the same signal the real Paperclip agents give. Until B's TaskWatcher
lands, the simulator announces the updates itself; once a watcher is running, it
only changes the mock and lets the watcher pick that up.
"""

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from company.types import Artifact, Issue, TaskResult
from gateway.events import EventBus
from gateway.roles import Role

log = logging.getLogger(__name__)

PROGRESS_NOTES = {
    "engineer": "Reproduced it with the failing test. Fixing Ryan's code. Again.",
    "sales_lead": "Researching Scranton-area businesses for the deck.",
    "cfo": "Building the spreadsheet. Numbers first, snacks second.",
    "eng_lead": "Writing up the spec. This is going to be huge.",
    "ceo": "Drafting it now. Personally.",
}
RESULTS = {  # role -> (summary template, artifact kind, file extension)
    "engineer": ("Fixed {title}. All tests pass now, and the diff is attached.", "diff", "diff"),
    "sales_lead": ("Done: {title}. Five new Scranton leads and a six-slide pitch deck.", "link", "md"),
    "cfo": ("Finished {title}. The model is in the spreadsheet, with every number checked twice.", "link", "md"),
}
DEFAULT_RESULT = ("Finished {title}. Notes are attached.", "link", "md")


class WorkSimulator:
    def __init__(
        self,
        company,
        roles: dict[str, Role],
        bus: EventBus,
        on_update: Callable[[Issue], Awaitable[None]],
        on_complete: Callable[[TaskResult], Awaitable[None]],
        *,
        work_seconds: float,
        start_seconds: float = 3.0,
        artifacts_dir: Path,
        public_url: str,
        announce_directly: Callable[[], bool] = lambda: True,
    ):
        self.company = company
        self.roles = roles
        self.bus = bus
        self.on_update = on_update
        self.on_complete = on_complete
        self.work_seconds = work_seconds
        self.start_seconds = start_seconds
        self.artifacts_dir = Path(artifacts_dir)
        self.public_url = public_url.rstrip("/")
        self.announce_directly = announce_directly
        self._seen: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._listener: asyncio.Task | None = None

    async def start(self) -> None:
        sub = self.bus.subscribe()  # subscribe now so no delegation is missed
        self._listener = asyncio.create_task(self._listen(sub))
        log.info("work simulator on: delegated tasks finish after %ss", self.work_seconds)

    async def stop(self) -> None:
        for t in [self._listener, *self._tasks]:
            if t is not None:
                t.cancel()
        await asyncio.gather(*(t for t in [self._listener, *self._tasks] if t), return_exceptions=True)

    async def _listen(self, sub) -> None:
        try:
            async for type, data in sub:
                if type == "task.updated" and data.get("status") == "todo":
                    self.task_started(data["task_id"])
        finally:
            sub.close()

    def task_started(self, task_id: str) -> None:
        if task_id in self._seen:
            return
        self._seen.add(task_id)
        task = asyncio.create_task(self._work(task_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _work(self, task_id: str) -> None:
        try:
            issue = await self.company.get_issue(task_id)
            if issue.origin != "voice" or issue.assignee_role is None:
                return
            role = issue.assignee_role
            await asyncio.sleep(self.start_seconds)
            self.company.set_status(task_id, "in_progress")
            await self.company.add_comment(task_id, PROGRESS_NOTES.get(role, "On it."))
            if self.announce_directly():
                await self.on_update(await self.company.get_issue(task_id))

            await asyncio.sleep(max(0.0, self.work_seconds - self.start_seconds))
            template, kind, ext = RESULTS.get(role, DEFAULT_RESULT)
            summary = template.format(title=issue.title)
            artifact = self._write_artifact(task_id, issue.title, summary, kind, ext)
            self.company.complete(task_id, summary, (artifact,))
            if self.announce_directly():
                await self.on_update(await self.company.get_issue(task_id))
                await self.on_complete(TaskResult(
                    task_id=task_id, title=issue.title, from_role=role,
                    requested_by_role=issue.requested_by_role, summary=summary, artifacts=[artifact],
                ))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("simulated work on %s failed", task_id)

    def _write_artifact(self, task_id: str, title: str, summary: str, kind: str, ext: str) -> Artifact:
        name = f"sim-{task_id}.{ext}"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if ext == "diff":
            body = ("--- a/src/pricing.js\n+++ b/src/pricing.js\n@@ (simulated) @@\n"
                    "-  const cases = order.quantity;\n+  const cases = order.cases;\n")
        else:
            body = f"# {title}\n\n(Simulated work result, not real output.)\n\n{summary}\n"
        (self.artifacts_dir / name).write_text(body)
        label = "The fix" if kind == "diff" else title
        return Artifact(kind=kind, url=f"{self.public_url}/artifacts/{name}", label=label)
