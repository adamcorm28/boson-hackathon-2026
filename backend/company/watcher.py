"""Poll the company for voice-originated tasks and report progress and completions.

A task is complete when its status is in_review or done AND it has a RESULT: comment
(see company.results). Each completion is reported exactly once. Tasks that are
already complete when the watcher starts are recorded but not announced, so a
gateway restart doesn't re-announce old work.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from company.results import parse_result
from company.types import CompanyAPI, CompanyUnavailable, Issue, TaskResult

log = logging.getLogger(__name__)

COMPLETE_STATUSES = ("in_review", "done")
MISSING_RESULT_WARN_SECONDS = 600


class TaskWatcher:
    def __init__(self, company: CompanyAPI, on_update: Callable[[Issue], Awaitable[None]],
                 on_complete: Callable[[TaskResult], Awaitable[None]], interval: float = 3.0,
                 clock: Callable[[], float] = time.monotonic):
        self._company = company
        self._on_update = on_update
        self._on_complete = on_complete
        self._interval = interval
        self._clock = clock
        self._seen: dict[str, tuple] = {}  # task_id -> (status, updated_at, comment count)
        self._announced: set[str] = set()
        self._awaiting_result_since: dict[str, float] = {}
        self._warned: set[str] = set()
        self._primed = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self._interval)

    async def poll_once(self) -> None:
        try:
            issues = [i for i in await self._company.list_issues() if i.origin == "voice"]
        except CompanyUnavailable as e:
            log.warning("task watcher: %s", e)
            return
        for issue in issues:
            await self._check(issue)
        self._primed = True

    async def _check(self, issue: Issue) -> None:
        # Paperclip's list has no comments (count stays 0) but bumps updated_at on each comment;
        # the mock includes comments. Either change is enough.
        key = (issue.status, issue.updated_at, len(issue.comments))
        changed = self._seen.get(issue.task_id) != key
        self._seen[issue.task_id] = key
        awaiting = issue.status in COMPLETE_STATUSES and issue.task_id not in self._announced
        if not (changed or awaiting):
            return
        try:
            full = await self._company.get_issue(issue.task_id)  # with comments
        except (KeyError, CompanyUnavailable) as e:
            log.warning("task watcher: can't read %s: %s", issue.task_id, e)
            return
        if changed and self._primed:
            await self._call(self._on_update, full)
        if awaiting:
            await self._check_result(full)

    async def _check_result(self, issue: Issue) -> None:
        parsed = parse_result(issue.comments)
        if parsed is None:
            since = self._awaiting_result_since.setdefault(issue.task_id, self._clock())
            if self._clock() - since > MISSING_RESULT_WARN_SECONDS and issue.task_id not in self._warned:
                self._warned.add(issue.task_id)
                log.warning("task %s is %s but has no RESULT: comment after %d minutes",
                            issue.task_id, issue.status, MISSING_RESULT_WARN_SECONDS // 60)
            return
        self._announced.add(issue.task_id)
        self._awaiting_result_since.pop(issue.task_id, None)
        if not self._primed:
            return  # already complete at startup: record, don't announce
        summary, artifacts = parsed
        await self._call(self._on_complete, TaskResult(
            task_id=issue.task_id, title=issue.title, from_role=issue.assignee_role,
            requested_by_role=issue.requested_by_role, summary=summary, artifacts=artifacts))

    async def _call(self, callback, arg) -> None:
        try:
            await callback(arg)
        except Exception:
            log.exception("task watcher callback %s failed", getattr(callback, "__name__", callback))
