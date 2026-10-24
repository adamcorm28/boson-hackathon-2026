import asyncio

from gateway.events import EventBus
from gateway.simulator import WorkSimulator


async def until(pred, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        if loop.time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


def make(company, roles, tmp_path, announce=True):
    bus = EventBus()
    updates, completions = [], []

    async def on_update(issue):
        updates.append((issue.task_id, issue.status))

    async def on_complete(result):
        completions.append(result)

    sim = WorkSimulator(company, roles, bus, on_update, on_complete, work_seconds=0.1, start_seconds=0.02,
                        artifacts_dir=tmp_path, public_url="http://localhost:8000/",
                        announce_directly=lambda: announce)
    return sim, bus, updates, completions


async def test_delegated_task_starts_then_completes(company, roles, tmp_path):
    sim, bus, updates, completions = make(company, roles, tmp_path)
    await sim.start()
    tid = await company.create_task("engineer", "Fix bulk discount", "b", "eng_lead")
    bus.publish("task.updated", {"task_id": tid, "status": "todo", "assignee_role": "engineer", "title": "x"})
    await until(lambda: (tid, "in_progress") in updates)
    assert (await company.get_agent_status("engineer")).state == "working"
    assert completions == []
    await until(lambda: completions)
    r = completions[0]
    assert r.task_id == tid and r.from_role == "engineer" and r.requested_by_role == "eng_lead"
    assert r.artifacts[0].kind == "diff"
    assert r.artifacts[0].url == f"http://localhost:8000/artifacts/sim-{tid}.diff"
    assert (tmp_path / f"sim-{tid}.diff").exists()
    issue = await company.get_issue(tid)
    assert issue.status == "done" and issue.comments[-1].body.startswith("RESULT: ")
    await sim.stop()


async def test_same_task_simulated_once(company, roles, tmp_path):
    sim, bus, updates, completions = make(company, roles, tmp_path)
    await sim.start()
    tid = await company.create_task("sales_lead", "Pitch deck", "b", "sales_lead")
    for _ in range(3):
        bus.publish("task.updated", {"task_id": tid, "status": "todo"})
    await until(lambda: completions)
    await asyncio.sleep(0.15)
    assert len(completions) == 1
    await sim.stop()


async def test_seed_tasks_are_ignored(company, roles, tmp_path):
    sim, bus, updates, completions = make(company, roles, tmp_path)
    await sim.start()
    bus.publish("task.updated", {"task_id": "DM-101", "status": "todo"})
    await asyncio.sleep(0.15)
    assert updates == [] and completions == []
    assert (await company.get_issue("DM-101")).status == "todo"
    await sim.stop()


async def test_with_watcher_running_only_mutates_mock(company, roles, tmp_path):
    sim, bus, updates, completions = make(company, roles, tmp_path, announce=False)
    await sim.start()
    tid = await company.create_task("engineer", "Fix bulk discount", "b", "eng_lead")
    bus.publish("task.updated", {"task_id": tid, "status": "todo"})
    await until(lambda: company._issues[tid].status == "done")
    assert updates == [] and completions == []
    await sim.stop()
