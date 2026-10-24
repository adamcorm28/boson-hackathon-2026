"""CallSession: one live call between the browser and a Higgs Realtime voice agent (spec §5).

Three loops run until one ends: browser -> upstream (mic audio, hangup),
upstream -> browser (audio, transcripts, tool calls), and the injector tick
that announces finished tasks in quiet gaps.
"""

import asyncio
import base64
import json
import logging
import re
import time
from typing import AsyncIterator, Awaitable, Callable, Protocol

import websockets

from company.types import TaskResult
from gateway.events import EventBus
from gateway.injector import NotificationQueue, TurnState, injection_events
from gateway.instructions import build_briefing, build_instructions
from gateway.memory import CallMemory, CallRecord
from gateway.roles import Role
from gateway.tools import CallContext, run_tool, tools_for

log = logging.getLogger(__name__)

TRANSCRIPTION_MODEL = "higgs-stt-3.1"
END_EVENTS = {"session.idle_timeout": "idle_timeout", "session.max_duration_reached": "max_duration_reached"}
FATAL_ERROR_CODES = {"idle_timeout", "session_expired", "max_duration_reached", "rate_limit_exceeded", "unauthorized"}
CLOSE_REASONS = {1013: "upstream_busy", 4429: "rate_limited"}
# The voice model sometimes says work is underway without calling delegate_task.
DELEGATION_CLAIM = re.compile(
    r"(\bon it\b|ping you|\bassign|delegat|i'?ll (have|get) \w+|"
    r"\b(he|she|they)('s| is| are) (started|starting|fixing|working|looking|building))",
    re.IGNORECASE,
)
# ...but only nudge when the user actually asked for work in their last turn.
USER_REQUEST = re.compile(
    r"\b(do it|go ahead|go for it|yes|yeah|yep|sure|okay|ok|please|have \w+|get \w+|can you|could you|"
    r"would you|fix|make|build|send|draft|write|research|put together|start|handle|take care|delegate|assign)\b",
    re.IGNORECASE,
)
DELEGATION_NUDGE = (
    "[notification from system, not the user] You just told the user the work is happening, but you "
    "never called delegate_task, so nobody is working on it. Call delegate_task now with the right "
    "assignee, title and brief. After it returns, say only a few words, like \"Done, he's started.\""
)


class Upstream(Protocol):
    async def send(self, message: str) -> None: ...
    def __aiter__(self) -> AsyncIterator[str]: ...
    async def close(self) -> None: ...


class ClientWS(Protocol):
    """The subset of starlette's WebSocket the session uses."""

    async def receive(self) -> dict: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def send_json(self, data: dict) -> None: ...


class CallSession:
    def __init__(
        self,
        role: Role,
        client_ws: ClientWS,
        connect_upstream: Callable[[], Awaitable[Upstream]],
        ctx: CallContext,
        queue: NotificationQueue,
        bus: EventBus,
        memory: CallMemory,
        mode: str = "user_message",
        clock: Callable[[], float] = time.monotonic,
        tick: float = 0.25,
    ):
        self.role = role
        self.client = client_ws
        self.connect_upstream = connect_upstream
        self.ctx = ctx
        self.ctx.on_task_started = self._on_task_started
        self.queue = queue
        self.bus = bus
        self.memory = memory
        self.mode = mode
        self.clock = clock
        self.tick = tick
        self.turn = TurnState()
        self.record: CallRecord = memory.start(role)
        self.upstream: Upstream | None = None
        self._client_open = True
        self._continuing = False  # tool output sent, waiting for the follow-up response
        self._inflight: TaskResult | None = None  # injected, awaiting its response.created
        self._reason = "ended"
        self._delegated_this_turn = False  # delegate_task ran since the user last spoke
        self._nudged_this_turn = False
        self._response_text = ""  # transcript of the response in progress
        self._last_user_text = ""

    # --- lifecycle ----------------------------------------------------------------------

    async def run(self) -> CallRecord:
        try:
            pending = self.queue.pending()
            briefing = await build_briefing(
                self.role, self.ctx.company, self.memory.recent_summaries(), pending, self.ctx.roles)
            instructions = build_instructions(self.role, briefing)
            self.queue.discard({r.task_id for r in pending})  # the briefing delivers them

            self.upstream = await self.connect_upstream()
            await self._send_upstream(self._session_update(instructions))
            await self._send_upstream({"type": "response.create"})  # the greeting (in the session instructions)
            await self._to_client({"type": "call.started", "role": self.role.id})
            self.bus.publish("agent.status", {"role": self.role.id, "state": "on_call"})

            tasks = [asyncio.create_task(c) for c in
                     (self._client_loop(), self._upstream_loop(), self._injector_loop())]
            done, pending_tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending_tasks:
                t.cancel()
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            for t in done:
                if t.exception():
                    log.error("call loop crashed", exc_info=t.exception())
                    self._reason = "error"
        except Exception:
            log.exception("call setup failed")
            self._reason = "error"
        finally:
            await self._shutdown()
        return self.record

    async def _shutdown(self) -> None:
        if self._inflight is not None:  # injected but never spoken
            self.queue.requeue_front(self._inflight)
        if self.upstream is not None:
            try:
                await self.upstream.close()
            except Exception:
                pass
        await self._to_client({"type": "call.ended", "reason": self._reason})
        self.bus.publish("agent.status", {"role": self.role.id, "state": "idle"})
        try:
            await self.memory.finish(self.record, self.ctx.company)
        except Exception:
            log.exception("saving call memory failed")

    def _session_update(self, instructions: str) -> dict:
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": instructions,
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "turn_detection": self.role.turn_detection or {"type": "server_vad"},
                        "transcription": {"model": TRANSCRIPTION_MODEL},
                    },
                    "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": self.role.voice},
                },
                "tools": tools_for(self.role),
            },
        }

    # --- io helpers ---------------------------------------------------------------------

    async def _send_upstream(self, event: dict) -> None:
        await self.upstream.send(json.dumps(event))

    async def _to_client(self, event: dict) -> None:
        if not self._client_open:
            return
        try:
            await self.client.send_json(event)
        except Exception:
            self._client_open = False

    async def _audio_to_client(self, pcm: bytes) -> None:
        if not self._client_open:
            return
        try:
            await self.client.send_bytes(pcm)
        except Exception:
            self._client_open = False

    async def _on_task_started(self, task_id: str, title: str, assignee_role: str) -> None:
        self.record.touched_task_ids.add(task_id)
        await self._to_client({"type": "task.started", "task_id": task_id, "title": title, "assignee_role": assignee_role})
        self.bus.publish("task.updated", {"task_id": task_id, "status": "todo", "assignee_role": assignee_role, "title": title})

    # --- loops --------------------------------------------------------------------------

    async def _client_loop(self) -> None:
        while True:
            try:
                msg = await self.client.receive()
            except Exception:
                msg = {"type": "websocket.disconnect"}
            if msg.get("type") == "websocket.disconnect":
                self._client_open = False
                self._reason = "client_disconnected"
                return
            if msg.get("bytes") is not None:
                await self._send_upstream({
                    "type": "input_audio_buffer.append", "audio": base64.b64encode(msg["bytes"]).decode()})
            elif msg.get("text") is not None:
                try:
                    data = json.loads(msg["text"])
                except ValueError:
                    continue
                if data.get("type") == "hangup":
                    self._reason = "hangup"
                    return

    async def _upstream_loop(self) -> None:
        try:
            async for raw in self.upstream:
                if isinstance(raw, bytes):
                    continue
                if await self._handle_upstream(json.loads(raw)):
                    return
            self._reason = "upstream_closed"
            log.info("upstream closed: code=%s reason=%s", getattr(self.upstream, "close_code", None),
                     getattr(self.upstream, "close_reason", None))
        except websockets.ConnectionClosed as e:
            log.info("upstream closed with error: %s", e)
            code = e.rcvd.code if e.rcvd else None
            self._reason = CLOSE_REASONS.get(code, "upstream_closed")

    async def _handle_upstream(self, ev: dict) -> bool:
        """Handle one upstream event; returns True when the call should end."""
        t = ev.get("type", "")
        now = self.clock()
        self.turn.on_upstream(t, now)
        match t:
            case "response.output_audio.delta":
                pcm = base64.b64decode(ev.get("delta", ""))
                self.turn.on_audio(len(pcm), now)
                await self._audio_to_client(pcm)
            case "response.output_audio_transcript.delta":
                await self._to_client({"type": "transcript.assistant.delta", "text": ev.get("delta", "")})
            case "response.output_audio_transcript.done":
                text = ev.get("transcript", "")
                self._response_text += " " + text
                self.record.transcript.append((self.role.id, text))
                await self._to_client({"type": "transcript.assistant.done", "text": text})
            case "conversation.item.input_audio_transcription.completed":
                text = ev.get("transcript", "")
                self.record.transcript.append(("user", text))
                self._last_user_text = text
                await self._to_client({"type": "transcript.user", "text": text})
            case "response.created":
                self._response_text = ""
                self._continuing = False
                self._inflight = None  # an injected notice is now being spoken
                await self._to_client({"type": "agent.speaking", "value": True})
            case "response.done":
                resp = ev.get("response", {})
                log.debug("response.done status=%s output=%s", resp.get("status"),
                         [o.get("name") or o.get("type") for o in resp.get("output", [])])
                await self._to_client({"type": "agent.speaking", "value": False})
                ran_tools = await self._run_function_calls(resp)
                if not ran_tools:
                    await self._guard_delegation()
            case "input_audio_buffer.speech_started":
                self._delegated_this_turn = self._nudged_this_turn = False
                if self._inflight is not None:  # user spoke before the notice started
                    self.queue.requeue_front(self._inflight)
                    self._inflight = None
                await self._to_client({"type": "barge_in"})
            case "error":
                err = ev.get("error") or {}
                log.warning("upstream error: %s", err)
                if err.get("code") in FATAL_ERROR_CODES or err.get("type") in FATAL_ERROR_CODES:
                    self._reason = err.get("code") or err.get("type")
                    return True
            case _ if t in END_EVENTS:
                self._reason = END_EVENTS[t]
                return True
        return False

    async def _guard_delegation(self) -> None:
        """If the agent claimed work is underway without delegating, make it delegate."""
        if ("delegate_task" not in self.role.voice_tools or not self.role.can_delegate_to
                or self._delegated_this_turn or self._nudged_this_turn or self._inflight
                or not DELEGATION_CLAIM.search(self._response_text)):
            return
        text = self._response_text.strip()
        if re.search(r"\balready\b", text, re.IGNORECASE) or text.endswith("?"):
            return  # past work, or offering rather than claiming
        if not USER_REQUEST.search(self._last_user_text):
            return  # small talk: the user didn't ask for anything
        self._nudged_this_turn = True
        log.info("agent claimed delegation without calling delegate_task; nudging")
        await self._send_upstream({
            "type": "conversation.item.create",
            "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": DELEGATION_NUDGE}]},
        })
        self._continuing = True
        await self._send_upstream({"type": "response.create"})

    async def _run_function_calls(self, response: dict) -> bool:
        fcs = [o for o in response.get("output", []) if o.get("type") == "function_call"]
        calls = [o for o in fcs if o.get("executor") in (None, "client")]  # executor may be absent or null
        for o in fcs:
            if o not in calls:
                log.info("skipping %s function call %s", o.get("executor"), o.get("name"))
        if not calls:
            return False
        self._continuing = True
        for call in calls:
            name = call.get("name", "")
            try:
                args = json.loads(call.get("arguments") or "{}")
            except ValueError:
                args = {}
            await self._to_client({"type": "tool.called", "name": name, "args": args})
            output = await run_tool(name, args, self.ctx)
            if name == "delegate_task" and output.get("status") == "started":
                self._delegated_this_turn = True
            if name == "get_issue" and "error" not in output and args.get("task_id"):
                self.record.touched_task_ids.add(args["task_id"])
            await self._send_upstream({
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call.get("call_id"), "output": json.dumps(output)},
            })
        await self._send_upstream({"type": "response.create"})
        return True

    async def _injector_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick)
            now = self.clock()
            if not self.queue or self._inflight or self._continuing or not self.turn.ready(now):
                continue
            result = self.queue.pop()
            for event in injection_events(result, self.role, self.ctx.roles, self.mode):
                await self._send_upstream(event)
            self.turn.mark_injected(now)
            self._inflight = result
            sender = self.ctx.roles.get(result.from_role)
            self.bus.publish("ping", {
                "to_role": self.role.id, "from_role": result.from_role, "task_id": result.task_id,
                "text": f"{sender.name if sender else result.from_role}: {result.title} is done",
            })
