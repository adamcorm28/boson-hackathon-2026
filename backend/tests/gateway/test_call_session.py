import asyncio
import base64
import json

import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from company.types import TaskResult
from gateway import app_state, http
from gateway.call_session import CallSession
from gateway.events import EventBus
from gateway.injector import NotificationQueue
from gateway.memory import CallMemory
from gateway.tools import CallContext


class FakeUpstream:
    """Yields scripted server events (fed by the test), records what the session sends."""

    def __init__(self):
        self.sent: list[dict] = []
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def feed(self, *events: dict) -> None:
        for e in events:
            self.inbox.put_nowait(json.dumps(e))

    def close_with(self, exc: Exception) -> None:
        self.inbox.put_nowait(exc)

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.inbox.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True

    def types(self) -> list[str]:
        return [e["type"] for e in self.sent]


class FakeClientWS:
    def __init__(self):
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.json: list[dict] = []
        self.binary: list[bytes] = []

    async def receive(self) -> dict:
        return await self.incoming.get()

    async def send_json(self, data: dict) -> None:
        self.json.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.binary.append(data)

    def disconnect(self) -> None:
        self.incoming.put_nowait({"type": "websocket.disconnect"})

    def types(self) -> list[str]:
        return [e["type"] for e in self.json]


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


async def fake_summary(transcript):
    return "summary"


async def until(pred, timeout=1.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        if loop.time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


@pytest.fixture
def harness(roles, company, tmp_path):
    class H:
        pass

    h = H()
    h.upstream = FakeUpstream()
    h.client = FakeClientWS()
    h.queue = NotificationQueue()
    h.bus = EventBus()
    h.events = h.bus.subscribe()
    h.memory = CallMemory(tmp_path, summarize_fn=fake_summary)
    h.clock = Clock()
    h.company = company

    def make(role_id="eng_lead", mode="user_message", live_avatar=None):
        async def connect():
            return h.upstream

        ctx = CallContext(role=roles[role_id], company=company, roles=roles, on_task_started=None)
        h.session = CallSession(roles[role_id], h.client, connect, ctx, h.queue, h.bus, h.memory,
                                mode=mode, clock=h.clock, tick=0.005, live_avatar=live_avatar)
        h.task = asyncio.create_task(h.session.run())
        return h.session

    async def drain_bus():
        out = []
        while True:
            try:
                out.append(await asyncio.wait_for(h.events.get(), 0.01))
            except asyncio.TimeoutError:
                return out

    h.make = make
    h.drain_bus = drain_bus
    return h


async def started(h):
    await until(lambda: "call.started" in h.client.types())


async def test_first_messages_are_session_update_then_greeting(harness, roles):
    harness.make("ceo")
    await started(harness)
    first, second = harness.upstream.sent[:2]
    assert first["type"] == "session.update"
    s = first["session"]
    assert s["audio"]["output"]["voice"] == roles["ceo"].voice
    assert s["audio"]["input"]["transcription"] == {"model": "higgs-stt-3.1"}
    assert s["output_modalities"] == ["audio"]
    assert "never read out IDs or URLs" in s["instructions"]
    assert {t.get("name") for t in s["tools"]} >= {"get_company_overview", "delegate_task"}
    assert second == {"type": "response.create"}  # per-response instructions break later tool use
    assert "World's Best Boss" in s["instructions"]
    assert ("agent.status", {"role": "ceo", "state": "on_call"}) in await harness.drain_bus()
    harness.client.disconnect()
    await harness.task


async def test_audio_delta_forwarded_as_binary(harness):
    harness.make()
    await started(harness)
    harness.upstream.feed({"type": "response.output_audio.delta", "delta": base64.b64encode(b"\x01\x02").decode()})
    await until(lambda: harness.client.binary == [b"\x01\x02"])
    harness.client.disconnect()
    await harness.task


async def test_mic_audio_forwarded_upstream(harness):
    harness.make()
    await started(harness)
    harness.client.incoming.put_nowait({"type": "websocket.receive", "bytes": b"\x00\x01"})
    await until(lambda: "input_audio_buffer.append" in harness.upstream.types())
    sent = next(e for e in harness.upstream.sent if e["type"] == "input_audio_buffer.append")
    assert base64.b64decode(sent["audio"]) == b"\x00\x01"
    harness.client.disconnect()
    await harness.task


async def test_transcripts_forwarded_and_recorded(harness):
    harness.make()
    await started(harness)
    harness.upstream.feed(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "What happened?"},
        {"type": "response.output_audio_transcript.delta", "delta": "The disc"},
        {"type": "response.output_audio_transcript.done", "transcript": "The discount broke."},
    )
    await until(lambda: "transcript.assistant.done" in harness.client.types())
    assert {"type": "transcript.user", "text": "What happened?"} in harness.client.json
    assert {"type": "transcript.assistant.delta", "text": "The disc"} in harness.client.json
    harness.client.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps({"type": "hangup"})})
    record = await harness.task
    assert record.transcript == [("user", "What happened?"), ("eng_lead", "The discount broke.")]
    assert harness.client.json[-1] == {"type": "call.ended", "reason": "hangup"}


async def test_client_function_call_runs_tool_and_continues(harness):
    harness.make("eng_lead")
    await started(harness)
    harness.upstream.feed({"type": "response.created"}, {"type": "response.done", "response": {"output": [{
        "type": "function_call", "name": "delegate_task", "call_id": "c1", "executor": "client",
        "arguments": json.dumps({"assignee": "engineer", "title": "Fix bulk discount", "brief": "pricing.js"}),
    }]}})
    await until(lambda: harness.upstream.types()[-1:] == ["response.create"] and len(harness.upstream.sent) > 2)
    out = harness.upstream.sent[-2]
    assert out["type"] == "conversation.item.create" and out["item"]["type"] == "function_call_output"
    assert out["item"]["call_id"] == "c1"
    assert json.loads(out["item"]["output"])["status"] == "started"
    assert {"type": "tool.called", "name": "delegate_task",
            "args": {"assignee": "engineer", "title": "Fix bulk discount", "brief": "pricing.js"}} in harness.client.json
    task_started = next(e for e in harness.client.json if e["type"] == "task.started")
    assert task_started["assignee_role"] == "engineer"
    bus = await harness.drain_bus()
    assert any(t == "task.updated" and d["task_id"] == task_started["task_id"] for t, d in bus)
    harness.client.disconnect()
    record = await harness.task
    assert task_started["task_id"] in record.touched_task_ids


async def test_server_executor_call_ignored(harness):
    harness.make("eng_lead")
    await started(harness)
    n = len(harness.upstream.sent)
    harness.upstream.feed({"type": "response.done", "response": {"output": [{
        "type": "function_call", "name": "web_search", "call_id": "s1", "executor": "server", "arguments": "{}",
    }]}})
    await until(lambda: {"type": "agent.speaking", "value": False} in harness.client.json)
    await asyncio.sleep(0.02)
    assert len(harness.upstream.sent) == n
    harness.client.disconnect()
    await harness.task


async def test_speech_started_sends_barge_in(harness):
    harness.make()
    await started(harness)
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"})
    await until(lambda: "barge_in" in harness.client.types())
    harness.client.disconnect()
    await harness.task


def injected(h) -> int:
    """How many notices were injected (user_message mode)."""
    return sum(e["type"] == "conversation.item.create" and e["item"].get("role") == "user" for e in h.upstream.sent)


def queued_result(from_role="engineer"):
    return TaskResult("DM-200", "Fix bulk discount", from_role, "eng_lead", "Fixed it.", [])


async def test_injection_after_quiet_gap(harness):
    harness.make("sales_lead")
    await started(harness)
    harness.upstream.feed({"type": "response.created"}, {"type": "response.done", "response": {"output": []}})
    await until(lambda: {"type": "agent.speaking", "value": False} in harness.client.json)
    harness.queue.push(queued_result())  # arrives mid-call
    await asyncio.sleep(0.03)
    assert not injected(harness)  # gap not over yet
    harness.clock.t += 2
    await until(lambda: injected(harness))
    assert harness.upstream.types()[-2:] == ["conversation.item.create", "response.create"]
    bus = await harness.drain_bus()
    ping = next(d for t, d in bus if t == "ping")
    assert ping["to_role"] == "sales_lead" and ping["from_role"] == "engineer" and ping["task_id"] == "DM-200"
    assert len(harness.queue) == 0
    harness.client.disconnect()
    await harness.task


async def test_speech_before_injected_response_requeues(harness):
    harness.make("sales_lead")
    await started(harness)
    harness.queue.push(queued_result())
    harness.clock.t += 2
    await until(lambda: injected(harness))
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"})
    await until(lambda: len(harness.queue) == 1)
    harness.client.disconnect()
    await harness.task


async def test_injected_notice_delivered_once_response_created(harness):
    harness.make("sales_lead")
    await started(harness)
    harness.queue.push(queued_result())
    harness.clock.t += 2
    await until(lambda: injected(harness))
    harness.upstream.feed({"type": "response.created"}, {"type": "input_audio_buffer.speech_started"})
    await until(lambda: "barge_in" in harness.client.types())
    assert len(harness.queue) == 0
    harness.client.disconnect()
    await harness.task


async def test_two_queued_results_need_a_user_turn_between(harness):
    harness.make("sales_lead")
    await started(harness)
    harness.queue.push(queued_result())
    harness.queue.push(TaskResult("DM-201", "Pitch deck", "sales_lead", "sales_lead", "Deck done.", []))
    harness.clock.t += 2
    await until(lambda: injected(harness))
    harness.upstream.feed({"type": "response.created"}, {"type": "response.done", "response": {"output": []}})
    harness.clock.t += 5
    await asyncio.sleep(0.05)
    assert injected(harness) == 1
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, {"type": "input_audio_buffer.speech_stopped"})
    await until(lambda: not harness.session.turn.user_speaking and not harness.session.turn.awaiting_user_turn)
    harness.clock.t += 2
    await until(lambda: injected(harness) == 2)
    harness.client.disconnect()
    await harness.task


async def test_pending_results_go_into_briefing_and_leave_queue(harness):
    harness.queue.push(queued_result())
    harness.make("eng_lead")
    await started(harness)
    assert "Fix bulk discount" in harness.upstream.sent[0]["session"]["instructions"]
    assert len(harness.queue) == 0
    harness.client.disconnect()
    await harness.task


async def test_idle_timeout_ends_call_with_reason(harness):
    harness.make()
    await started(harness)
    harness.upstream.feed({"type": "session.idle_timeout"})
    await harness.task
    assert harness.client.json[-1] == {"type": "call.ended", "reason": "idle_timeout"}
    assert harness.upstream.closed


async def test_upstream_close_1013_ends_call(harness):
    harness.make()
    await started(harness)
    harness.upstream.close_with(websockets.ConnectionClosedError(websockets.frames.Close(1013, "busy"), None))
    await harness.task
    assert harness.client.json[-1] == {"type": "call.ended", "reason": "upstream_busy"}


async def test_client_disconnect_closes_upstream_and_saves_call(harness, tmp_path):
    harness.make()
    await started(harness)
    harness.upstream.feed({"type": "response.created"})  # mid-response
    await until(lambda: {"type": "agent.speaking", "value": True} in harness.client.json)
    harness.client.disconnect()
    record = await harness.task
    assert harness.upstream.closed
    assert (tmp_path / f"{record.call_id}.json").exists()
    bus = await harness.drain_bus()
    assert bus[-1] == ("agent.status", {"role": "eng_lead", "state": "idle"})


def test_second_call_rejected_4409(monkeypatch, roles, company, tmp_path):
    monkeypatch.setattr(app_state, "roles", roles)
    monkeypatch.setattr(app_state, "company", company)
    monkeypatch.setattr(app_state, "memory", CallMemory(tmp_path, summarize_fn=fake_summary))
    monkeypatch.setattr(app_state, "active_call", object())
    app = FastAPI()
    app.include_router(http.router)
    with TestClient(app).websocket_connect("/call/ceo") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4409


def test_call_route_end_to_end_with_fake_upstream(monkeypatch, roles, company, tmp_path):
    upstream = FakeUpstream()

    async def connect():
        return upstream

    monkeypatch.setattr(app_state, "roles", roles)
    monkeypatch.setattr(app_state, "company", company)
    monkeypatch.setattr(app_state, "bus", EventBus())
    monkeypatch.setattr(app_state, "queue", NotificationQueue())
    monkeypatch.setattr(app_state, "memory", CallMemory(tmp_path, summarize_fn=fake_summary))
    monkeypatch.setattr(app_state, "connect_upstream", connect)
    monkeypatch.setattr(app_state, "active_call", None)
    app = FastAPI()
    app.include_router(http.router)
    with TestClient(app).websocket_connect("/call/ceo") as ws:
        assert ws.receive_json() == {"type": "call.started", "role": "ceo"}
        assert app_state.active_call is not None
        ws.send_json({"type": "hangup"})
        assert ws.receive_json() == {"type": "call.ended", "reason": "hangup"}
    assert app_state.active_call is None


async def test_null_executor_treated_as_client(harness):
    harness.make("eng_lead")
    await started(harness)
    harness.upstream.feed({"type": "response.done", "response": {"output": [{
        "type": "function_call", "name": "get_my_work", "call_id": "c9", "executor": None, "arguments": "{}",
    }]}})
    await until(lambda: any(e["type"] == "conversation.item.create" and e["item"].get("call_id") == "c9"
                            for e in harness.upstream.sent))
    harness.client.disconnect()
    await harness.task


def nudges(h) -> int:
    return sum(e["type"] == "conversation.item.create" and "never called delegate_task" in json.dumps(e)
               for e in h.upstream.sent)


def say(text):
    return [{"type": "response.created"},
            {"type": "response.output_audio_transcript.done", "transcript": text},
            {"type": "response.done", "response": {"output": []}}]


def user_says(text):
    return {"type": "conversation.item.input_audio_transcription.completed", "transcript": text}


async def test_claimed_delegation_without_tool_gets_nudged_once(harness):
    harness.make("eng_lead")
    await started(harness)
    harness.upstream.feed(user_says("Okay, do it."), *say("Dwight's on it. I'll ping you when he's done."))
    await until(lambda: nudges(harness) == 1)
    assert harness.upstream.types()[-1] == "response.create"
    harness.upstream.feed(*say("Dwight's on it."))  # same user turn: no second nudge
    await asyncio.sleep(0.05)
    assert nudges(harness) == 1
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, user_says("Have him fix it."),
                          *say("He's on it."))
    await until(lambda: nudges(harness) == 2)  # new user turn: guard re-arms
    harness.client.disconnect()
    await harness.task


async def test_no_nudge_after_real_delegation(harness):
    harness.make("eng_lead")
    await started(harness)
    harness.upstream.feed({"type": "response.created"}, {"type": "response.done", "response": {"output": [{
        "type": "function_call", "name": "delegate_task", "call_id": "c1", "executor": "client",
        "arguments": json.dumps({"assignee": "engineer", "title": "Fix it", "brief": "b"}),
    }]}}, *say("Dwight's on it. I'll ping you."))
    await until(lambda: "task.started" in harness.client.types())
    await asyncio.sleep(0.05)
    assert nudges(harness) == 0
    # a later turn talking about the same work must not create a duplicate
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, *say("Dwight's already on it."))
    await asyncio.sleep(0.05)
    assert nudges(harness) == 0
    harness.client.disconnect()
    await harness.task


async def test_no_nudge_without_a_user_request(harness):
    harness.make("engineer")
    await started(harness)
    harness.upstream.feed(*say("I'm on it. Beets first."))
    await asyncio.sleep(0.05)
    assert nudges(harness) == 0
    harness.client.disconnect()
    await harness.task


async def test_no_nudge_for_small_talk_claims(harness):
    # real transcript: the persona invented past work during small talk, which created a junk task
    harness.make("ceo")
    await started(harness)
    harness.upstream.feed(user_says("Hey, how's your day going?"),
                          *say("Great! I've assigned Dwight to the evacuation routes. He's working on it."))
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, user_says("Can you fix the bug?"),
                          *say("I've already assigned Dwight to it."))
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, user_says("Please sort out the bug."),
                          *say("I can get Dwight on it. Want me to assign it?"))
    await asyncio.sleep(0.1)
    assert nudges(harness) == 0
    harness.client.disconnect()
    await harness.task


def lookup_nudges(h) -> int:
    return sum(e["type"] == "conversation.item.create" and "you didn't call a tool" in json.dumps(e)
               for e in h.upstream.sent)


async def test_lookup_claim_without_tool_gets_nudged_once_per_turn(harness):
    # real transcript: "Let me check your inbox real quick." then "I'm checking your inbox right now." forever
    harness.make("ceo")
    await started(harness)
    harness.upstream.feed(user_says("Is there anything in my inbox?"), *say("Let me check your inbox real quick."))
    await until(lambda: lookup_nudges(harness) == 1)
    harness.upstream.feed(*say("I'm checking your inbox right now."))  # same turn: once only
    await asyncio.sleep(0.05)
    assert lookup_nudges(harness) == 1
    harness.upstream.feed({"type": "input_audio_buffer.speech_started"}, user_says("Still checking?"),
                          *say("I'm checking your inbox right now."))
    await until(lambda: lookup_nudges(harness) == 2)
    harness.client.disconnect()
    await harness.task


async def test_no_lookup_nudge_when_tool_was_called(harness):
    harness.make("ceo")
    await started(harness)
    harness.upstream.feed({"type": "response.created"},
                          {"type": "response.output_audio_transcript.done", "transcript": "Let me check your inbox."},
                          {"type": "response.done", "response": {"output": [{
                              "type": "function_call", "name": "read_inbox", "call_id": "r1", "arguments": "{}"}]}})
    await until(lambda: "tool.called" in harness.client.types())
    await asyncio.sleep(0.05)
    assert lookup_nudges(harness) == 0
    harness.client.disconnect()
    await harness.task


class FakeLiveAvatar:
    def __init__(self, fail=False):
        self.fail = fail
        self.pushed: list = []
        self.closed = False

    async def join(self):
        return {"url": "wss://x.livekit.cloud", "token": "viewer-jwt", "avatar_identity": "boson-avatar"}

    async def summon(self):
        if self.fail:
            raise RuntimeError("no capacity")

    def push(self, pcm):
        self.pushed.append(pcm)

    def end_reply(self):
        self.pushed.append("flush")

    def interrupt(self):
        self.pushed.append("interrupt")

    def drain(self):
        out, self.pushed = [p for p in self.pushed if isinstance(p, bytes)], []
        return out

    async def close(self):
        self.closed = True


async def test_live_avatar_gets_the_speech_and_the_browser_gets_the_room(harness):
    live = FakeLiveAvatar()
    harness.make(live_avatar=live)
    await started(harness)
    await until(lambda: "avatar.room" in harness.client.types())
    room = next(e for e in harness.client.json if e["type"] == "avatar.room")
    assert room["token"] == "viewer-jwt"
    harness.upstream.feed(
        {"type": "response.created"},
        {"type": "response.output_audio.delta", "delta": base64.b64encode(b"\x01\x02").decode()},
        {"type": "response.done", "response": {"output": []}},
        {"type": "input_audio_buffer.speech_started"},
    )
    await until(lambda: "interrupt" in live.pushed)
    assert live.pushed == [b"\x01\x02", "flush", "interrupt"]
    assert harness.client.binary == []
    harness.client.disconnect()
    await harness.task
    assert live.closed


async def test_live_avatar_failure_falls_back_to_plain_audio(harness):
    live = FakeLiveAvatar(fail=True)
    live.pushed.append(b"\x05\x06")  # greeting audio queued while it was starting
    harness.make(live_avatar=live)
    await until(lambda: harness.client.binary == [b"\x05\x06"])
    assert harness.session.live is None and live.closed
    harness.upstream.feed({"type": "response.output_audio.delta", "delta": base64.b64encode(b"\x07\x08").decode()})
    await until(lambda: harness.client.binary == [b"\x05\x06", b"\x07\x08"])
    assert {"type": "avatar.unavailable", "reason": "error"} in harness.client.json
    harness.client.disconnect()
    await harness.task
