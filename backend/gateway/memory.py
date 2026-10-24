"""Cross-call memory (spec §5.5): saved transcripts plus a 2-sentence summary per call."""

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic

from company.types import CompanyAPI, CompanyUnavailable
from gateway.roles import Role

log = logging.getLogger(__name__)

CALLS_DIR = Path(os.getenv("CALLS_DIR", Path(__file__).parent.parent / "data" / "calls"))
SUMMARY_MODEL = "claude-haiku-5-5"
SUMMARY_PROMPT = "Summarize this call in 2 sentences for a colleague. Plain prose, no preamble."


@dataclass
class CallRecord:
    call_id: str
    role: str
    role_name: str
    started_at: float  # wall clock
    ended_at: float | None = None
    transcript: list[tuple[str, str]] = field(default_factory=list)  # (speaker role id or "user", text)
    touched_task_ids: set[str] = field(default_factory=set)
    summary: str = ""


def _lines(transcript: list[tuple[str, str]]) -> list[str]:
    return [f"{speaker}: {text}" for speaker, text in transcript]


async def summarize(transcript: list[tuple[str, str]], client: anthropic.AsyncAnthropic | None = None) -> str:
    if not transcript:
        return "No conversation."
    try:
        client = client or anthropic.AsyncAnthropic(timeout=10.0)
        resp = await client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": f"{SUMMARY_PROMPT}\n\n" + "\n".join(_lines(transcript))}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text:
            return text
    except Exception as e:
        log.warning("call summary failed, using last lines: %s", e)
    return " / ".join(_lines(transcript)[-6:])


class CallMemory:
    def __init__(self, dir: Path = CALLS_DIR, summarize_fn=summarize):
        self.dir = Path(dir)
        self.summarize_fn = summarize_fn
        self._records: list[CallRecord] = []
        for path in sorted(self.dir.glob("*.json")) if self.dir.exists() else []:
            try:
                raw = json.loads(path.read_text())
                raw["transcript"] = [tuple(t) for t in raw["transcript"]]
                raw["touched_task_ids"] = set(raw["touched_task_ids"])
                self._records.append(CallRecord(**raw))
            except Exception:
                log.warning("skipping unreadable call file %s", path)
        self._records.sort(key=lambda r: r.ended_at or r.started_at)

    def start(self, role: Role) -> CallRecord:
        return CallRecord(call_id=uuid.uuid4().hex[:12], role=role.id, role_name=role.name, started_at=time.time())

    async def finish(self, record: CallRecord, company: CompanyAPI) -> None:
        record.ended_at = time.time()
        record.summary = await self.summarize_fn(record.transcript)
        self.dir.mkdir(parents=True, exist_ok=True)
        data = asdict(record)
        data["touched_task_ids"] = sorted(record.touched_task_ids)
        (self.dir / f"{record.call_id}.json").write_text(json.dumps(data, indent=2))
        self._records.append(record)
        for task_id in sorted(record.touched_task_ids):
            try:
                # Paperclip wakes the assignee on every human comment and reopens a done task to todo, so a
                # note on a delegated task means a wasted rerun. Its brief already carries the call's ask.
                if (await company.get_issue(task_id)).origin == "voice":
                    continue
                await company.add_comment(task_id, f"Call note: {record.summary}")
            except (CompanyUnavailable, KeyError) as e:
                log.warning("couldn't add call note to %s: %r", task_id, e)

    def recent_summaries(self, n: int = 3) -> list[str]:
        now = time.time()
        out = []
        for r in reversed(self._records[-n:]):
            minutes = int((now - (r.ended_at or r.started_at)) // 60)
            out.append(f"With {r.role_name} ({minutes} min ago): {r.summary}")
        return out
