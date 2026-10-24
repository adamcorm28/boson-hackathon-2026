import json

from company.types import CompanyUnavailable
from gateway.memory import CallMemory, summarize


class Boom:
    class messages:
        @staticmethod
        async def create(**kwargs):
            raise RuntimeError("no network")


class Echo:
    def __init__(self):
        self.kwargs = None
        outer = self

        class messages:
            @staticmethod
            async def create(**kwargs):
                outer.kwargs = kwargs

                class R:
                    content = [type("B", (), {"type": "text", "text": "They talked about the bug."})()]
                return R()

        self.messages = messages


async def fake_summary(transcript):
    return f"{len(transcript)} lines"


async def test_summarize_fallback_last_six_lines():
    transcript = [("user" if n % 2 else "eng_lead", f"line {n}") for n in range(1, 8)]
    out = await summarize(transcript, client=Boom())
    assert "line 7" in out and "line 2" in out
    assert "line 1" not in out


async def test_summarize_uses_haiku():
    client = Echo()
    out = await summarize([("user", "hi"), ("ceo", "hello")], client=client)
    assert out == "They talked about the bug."
    assert client.kwargs["model"] == "claude-haiku-5-5"
    assert client.kwargs["max_tokens"] == 150
    assert "Summarize this call in 2 sentences for a colleague" in json.dumps(client.kwargs)


async def test_finish_writes_file_and_comments_touched_tasks(tmp_path, roles, company):
    mem = CallMemory(tmp_path, summarize_fn=fake_summary)
    rec = mem.start(roles["eng_lead"])
    rec.transcript += [("user", "fix it"), ("eng_lead", "on it")]
    rec.touched_task_ids.add("DM-101")
    await mem.finish(rec, company)
    saved = json.loads((tmp_path / f"{rec.call_id}.json").read_text())
    assert saved["summary"] == "2 lines" and saved["role"] == "eng_lead"
    assert saved["touched_task_ids"] == ["DM-101"]
    issue = await company.get_issue("DM-101")
    assert issue.comments[-1].body == "Call note: 2 lines"


async def test_recent_summaries_newest_first_limit_3(tmp_path, roles, company):
    mem = CallMemory(tmp_path, summarize_fn=fake_summary)
    for n, role in enumerate(["ceo", "eng_lead", "engineer", "sales_lead"]):
        rec = mem.start(roles[role])
        rec.transcript = [("user", "x")] * (n + 1)
        await mem.finish(rec, company)
    out = mem.recent_summaries()
    assert len(out) == 3
    assert out[0].startswith("With Jim Halpert (0 min ago): 4 lines")
    assert out[2].startswith("With Ryan Howard")


async def test_recent_summaries_survive_restart(tmp_path, roles, company):
    mem = CallMemory(tmp_path, summarize_fn=fake_summary)
    rec = mem.start(roles["ceo"])
    rec.transcript = [("user", "x")]
    await mem.finish(rec, company)
    assert CallMemory(tmp_path, summarize_fn=fake_summary).recent_summaries()[0].startswith("With Michael Scott")


async def test_finish_tolerates_company_unavailable(tmp_path, roles):
    class Down:
        async def add_comment(self, task_id, body):
            raise CompanyUnavailable()

    mem = CallMemory(tmp_path, summarize_fn=fake_summary)
    rec = mem.start(roles["ceo"])
    rec.touched_task_ids.add("DM-101")
    await mem.finish(rec, Down())
    assert (tmp_path / f"{rec.call_id}.json").exists()
