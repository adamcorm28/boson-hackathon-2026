import asyncio
import logging

import pytest

from company.mock import MockCompany
from company.types import Artifact, CompanyUnavailable, TaskResult
from company.watcher import TaskWatcher


class Recorder:
    def __init__(self):
        self.updates, self.completions = [], []

    async def on_update(self, issue):
        self.updates.append((issue.task_id, issue.status))

    async def on_complete(self, result):
        self.completions.append(result)


@pytest.fixture
def company():
    return MockCompany()


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def watcher(company, rec):
    return TaskWatcher(company, rec.on_update, rec.on_complete, interval=0.01)


async def test_complete_fires_once(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix bulk discount", "brief", "eng_lead")
    await watcher.poll_once()
    assert rec.completions == []
    company.complete(tid, "Fixed the discount.", (Artifact("diff", "http://x/fix.diff", "The fix"),))
    await watcher.poll_once()
    await watcher.poll_once()
    assert rec.completions == [TaskResult(
        task_id=tid, title="Fix bulk discount", from_role="engineer", requested_by_role="eng_lead",
        summary="Fixed the discount.", artifacts=[Artifact("diff", "http://x/fix.diff", "The fix")])]


async def test_status_done_without_result_does_not_fire(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.set_status(tid, "done")
    await watcher.poll_once()
    assert rec.completions == []


async def test_result_posted_after_done_fires_on_later_poll(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.set_status(tid, "done")
    await watcher.poll_once()
    await company.add_comment(tid, "RESULT: Fixed it after all.")
    await watcher.poll_once()
    assert [r.summary for r in rec.completions] == ["Fixed it after all."]


async def test_already_complete_at_start_not_announced(company, rec, watcher):
    tid = await company.create_task("engineer", "Old fix", "brief", "eng_lead")
    company.complete(tid, "Done long ago.")
    await watcher.poll_once()
    await watcher.poll_once()
    assert rec.completions == [] and rec.updates == []


async def test_update_fires_on_status_change(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.set_status(tid, "in_progress")
    await watcher.poll_once()
    await watcher.poll_once()
    assert rec.updates == [(tid, "in_progress")]


async def test_update_fires_on_new_comment(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    await company.add_comment(tid, "Found the root cause.")
    await watcher.poll_once()
    assert rec.updates == [(tid, "todo")]


async def test_new_task_after_start_fires_update(company, rec, watcher):
    await watcher.poll_once()
    tid = await company.create_task("sales_lead", "Prospect deck", "brief", "sales_lead")
    await watcher.poll_once()
    assert rec.updates == [(tid, "todo")]


async def test_seed_issues_ignored(company, rec, watcher):
    await watcher.poll_once()
    company.set_status("DM-101", "in_progress")
    company.complete("DM-102", "Numbers sent.")
    await watcher.poll_once()
    assert rec.updates == [] and rec.completions == []


async def test_unavailable_does_not_crash(rec):
    class Down:
        async def list_issues(self, role=None, status=None):
            raise CompanyUnavailable("Paperclip is down")

    await TaskWatcher(Down(), rec.on_update, rec.on_complete).poll_once()


async def test_missing_result_warns_once_after_ten_minutes(company, rec, caplog):
    now = [1000.0]
    watcher = TaskWatcher(company, rec.on_update, rec.on_complete, clock=lambda: now[0])
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.set_status(tid, "done")
    await watcher.poll_once()
    with caplog.at_level(logging.WARNING, logger="company.watcher"):
        now[0] += 599
        await watcher.poll_once()
        assert not caplog.records
        now[0] += 2
        await watcher.poll_once()
        await watcher.poll_once()
    assert len([r for r in caplog.records if tid in r.getMessage()]) == 1


async def test_callback_error_does_not_stop_watcher(company, rec):
    async def broken(issue):
        raise RuntimeError("gateway bug")

    watcher = TaskWatcher(company, broken, rec.on_complete)
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.complete(tid, "Fixed.")
    await watcher.poll_once()
    assert [r.summary for r in rec.completions] == ["Fixed."]


async def test_start_stop_polls_periodically(company, rec, watcher):
    await watcher.start()
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await asyncio.sleep(0.05)
    company.complete(tid, "Fixed.")
    await asyncio.sleep(0.05)
    await watcher.stop()
    assert [r.task_id for r in rec.completions] == [tid]


# --- failed runs (B10 dry run: a run died with acpx_turn_failed, no RESULT, nobody was told) ---------


async def test_failed_run_reported_once(company, rec, watcher):
    tid = await company.create_task("cfo", "Lackawanna model", "brief", "ceo")
    company.set_status(tid, "in_progress")
    await watcher.poll_once()
    company.fail(tid, "acpx_turn_failed")
    await watcher.poll_once()
    await watcher.poll_once()
    assert len(rec.completions) == 1
    result = rec.completions[0]
    assert result.failed and result.task_id == tid and result.from_role == "cfo"
    assert "couldn't finish" in result.summary


async def test_failure_noticed_without_any_issue_change(company, rec):
    # Paperclip doesn't touch the issue when a run fails, so the watcher re-checks pending tasks.
    watcher = TaskWatcher(company, rec.on_update, rec.on_complete, failure_check_every=2)
    tid = await company.create_task("cfo", "Lackawanna model", "brief", "ceo")
    await watcher.poll_once()
    company.fail(tid, "acpx_turn_failed", touch=False)
    await watcher.poll_once()
    assert rec.completions == []
    await watcher.poll_once()
    assert [r.failed for r in rec.completions] == [True]


async def test_already_failed_at_start_not_announced(company, rec, watcher):
    tid = await company.create_task("cfo", "Old model", "brief", "ceo")
    company.fail(tid, "acpx_turn_failed")
    await watcher.poll_once()
    await watcher.poll_once()
    assert rec.completions == []


async def test_successful_result_is_not_failed(company, rec, watcher):
    tid = await company.create_task("engineer", "Fix", "brief", "eng_lead")
    await watcher.poll_once()
    company.complete(tid, "Fixed.")
    await watcher.poll_once()
    assert [r.failed for r in rec.completions] == [False]
