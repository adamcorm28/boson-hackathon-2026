"""Quiet-gap injection of finished-task notices into a live call (spec §5.4).

Spike findings (docs/superpowers/spikes/realtime-findings.md) that shape this:
- Audio is generated faster than real time, so `response.done` arrives seconds
  before the browser finishes playing. The gate also waits for the estimated
  playback end (bytes received / 48 000 bytes per second).
- Per-response `instructions` make the model ignore the injected content, so the
  announcement guidance travels inside the injected payload instead.
"""

import json
import re
import uuid
from collections import deque
from typing import Literal

from company.types import TaskResult
from gateway.roles import Role

QUIET_GAP_S = 1.5
PCM_BYTES_PER_S = 24000 * 2  # 24 kHz mono PCM16
NOTIFICATION_PREFIX = "[notification from system, not the user]"


class TurnState:
    def __init__(self) -> None:
        self.response_active = False
        self.user_speaking = False
        self.awaiting_user_turn = False  # set by mark_injected: never two notices back to back
        self._last_turn_end = float("-inf")
        self._playback_end = float("-inf")

    def on_upstream(self, event_type: str, now: float) -> None:
        match event_type:
            case "response.created":
                self.response_active = True
            case "response.done":
                self.response_active = False
                self._last_turn_end = max(self._last_turn_end, now)
            case "input_audio_buffer.speech_started":
                self.user_speaking = True
                self.awaiting_user_turn = False
                self._playback_end = now  # the browser stops playback on barge_in
            case "input_audio_buffer.speech_stopped":
                self.user_speaking = False
                self._last_turn_end = max(self._last_turn_end, now)

    def on_audio(self, nbytes: int, now: float) -> None:
        self._playback_end = max(self._playback_end, now) + nbytes / PCM_BYTES_PER_S

    def ready(self, now: float) -> bool:
        if self.response_active or self.user_speaking or self.awaiting_user_turn:
            return False
        return now >= max(self._last_turn_end, self._playback_end) + QUIET_GAP_S

    def mark_injected(self, now: float) -> None:
        self.awaiting_user_turn = True


class NotificationQueue:
    """FIFO of finished results waiting to be announced; a task id is queued at most once."""

    def __init__(self) -> None:
        self._items: deque[TaskResult] = deque()

    def push(self, result: TaskResult) -> None:
        if all(r.task_id != result.task_id for r in self._items):
            self._items.append(result)

    def pop(self) -> TaskResult | None:
        return self._items.popleft() if self._items else None

    def requeue_front(self, result: TaskResult) -> None:
        if all(r.task_id != result.task_id for r in self._items):
            self._items.appendleft(result)

    def discard(self, task_ids: set[str]) -> None:
        self._items = deque(r for r in self._items if r.task_id not in task_ids)

    def pending(self) -> list[TaskResult]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


def _team(role: Role | None) -> str:
    if role is None:
        return "another team"
    m = re.search(r"\(([^)]+)\)", role.title)
    return m.group(1) if m else role.title


def announcement_guidance(result: TaskResult, active_role: Role, roles: dict[str, Role]) -> str:
    sender = roles.get(result.from_role)
    name = sender.name.split()[0] if sender else result.from_role
    own = active_role.id in (result.requested_by_role, result.from_role)
    if result.failed:
        who = "your" if own else f"{name}'s"
        return (f"Briefly tell the user that {who} work on {result.title} couldn't finish because the run hit an error, "
                "and offer to try it again. One or two short spoken sentences; don't read out IDs or error codes.")
    if own:
        return ("Briefly tell the user this is ready and ask if they want to go through it now. "
                "One or two short spoken sentences; don't read out IDs or links.")
    return (f"Mention naturally that {name} from {_team(sender)} just pinged that {result.title} is done; "
            f"offer to keep going or suggest they call {name}. One or two short spoken sentences.")


def injection_events(
    result: TaskResult,
    active_role: Role,
    roles: dict[str, Role],
    mode: Literal["function_call", "user_message"],
) -> list[dict]:
    sender = roles.get(result.from_role)
    from_name = sender.name if sender else result.from_role
    guidance = announcement_guidance(result, active_role, roles)
    if mode == "function_call":
        call_id = f"call_{uuid.uuid4().hex[:24]}"
        payload = {
            "task_id": result.task_id, "from_role": result.from_role, "from_name": from_name,
            "title": result.title, "result_summary": result.summary, "how_to_mention_it": guidance,
        }
        return [
            {"type": "conversation.item.create",
             "item": {"type": "function_call", "name": "task_update", "call_id": call_id, "arguments": "{}"}},
            {"type": "conversation.item.create",
             "item": {"type": "function_call_output", "call_id": call_id, "output": json.dumps(payload)}},
            {"type": "response.create"},
        ]
    outcome = "couldn't finish" if result.failed else "finished"
    text = (f"{NOTIFICATION_PREFIX} {from_name} {outcome} \"{result.title}\". "
            f"Summary: {result.summary} How to mention it: {guidance}")
    return [
        {"type": "conversation.item.create",
         "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
        {"type": "response.create"},
    ]
