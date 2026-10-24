"""Throwaway spike for Higgs Realtime (plan task A1): voices, injection, interruption.

Usage (from backend/):
    .venv/bin/python spikes/realtime_spike.py voices
    .venv/bin/python spikes/realtime_spike.py inject --mode function_call [--wait 20]
    .venv/bin/python spikes/realtime_spike.py inject --mode user_message
    .venv/bin/python spikes/realtime_spike.py interrupt --mode function_call
    .venv/bin/python spikes/realtime_spike.py raw '{"type": "session.update", ...}'

Writes WAVs and event logs to spikes/out/.
"""

import argparse
import asyncio
import base64
import json
import os
import ssl
import sys
import time
import uuid
import wave
from pathlib import Path

import certifi
import httpx
import websockets
from dotenv import load_dotenv

HERE = Path(__file__).parent
OUT = HERE / "out"
load_dotenv(HERE.parent / ".env")

API_KEY = os.environ["BOSON_API_KEY"]
ENDPOINT = os.getenv("REALTIME_ENDPOINT", "wss://api.boson.ai/v1/realtime")
MODEL = os.getenv("REALTIME_MODEL", "higgs-realtime")
URL = f"{ENDPOINT}?model={MODEL}"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
SSL = ssl.create_default_context(cafile=certifi.where())
VOICES = ["default", "marcus", "jake", "oliver", "chloe", "eleanor", "nora"]

DELEGATE_TOOL = {
    "type": "function",
    "name": "delegate_task",
    "description": "Hand slow work (fixes, research, decks) to a teammate. Returns immediately.",
    "parameters": {
        "type": "object",
        "properties": {
            "assignee": {"type": "string", "enum": ["engineer"]},
            "title": {"type": "string"},
            "brief": {"type": "string"},
        },
        "required": ["assignee", "title", "brief"],
    },
}
OWN_TASK_INSTRUCTIONS = (
    "A task you delegated just finished. Briefly tell the user this is ready and ask if "
    "they want to go through it now. One or two short spoken sentences."
)
PERSONA = (
    "You are Ryan Howard, engineering lead at Dunder Mifflin Scranton. Short spoken "
    "sentences. Never read out IDs or URLs. Use delegate_task for anything slow."
)


def session_update(voice: str, tools: list | None = None, instructions: str = PERSONA) -> dict:
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "turn_detection": {"type": "server_vad"},
                    "transcription": {"model": "higgs-stt-3.1"},
                },
                "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": voice},
            },
            "tools": tools or [],
        },
    }


def user_text(text: str) -> dict:
    return {
        "type": "conversation.item.create",
        "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
    }


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)


class Session:
    """Thin wrapper: logs every event, collects audio and transcripts."""

    def __init__(self, ws, log_name: str):
        self.ws = ws
        self.t0 = time.monotonic()
        self.log = (OUT / f"{log_name}.events.jsonl").open("w")
        self.audio = bytearray()
        self.transcript: list[str] = []
        self.seen_types: list[str] = []

    async def send(self, event: dict) -> None:
        self.log.write(json.dumps({"t": round(time.monotonic() - self.t0, 2), "sent": event}) + "\n")
        print(f"  -> {event['type']}")
        await self.ws.send(json.dumps(event))

    async def recv_until(self, predicate, timeout: float = 30.0) -> dict | None:
        """Read events until predicate(event) is true; returns that event (or None on timeout)."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                raw = await asyncio.wait_for(self.ws.recv(), remaining)
            except asyncio.TimeoutError:
                return None
            ev = json.loads(raw)
            self._record(ev)
            if predicate(ev):
                return ev

    def _record(self, ev: dict) -> None:
        t = ev.get("type", "?")
        self.seen_types.append(t)
        logged = dict(ev)
        if t == "response.output_audio.delta":
            self.audio.extend(base64.b64decode(ev["delta"]))
            logged["delta"] = f"<{len(ev['delta'])} b64 chars>"
        else:
            print(f"  <- {t}" + (f" {json.dumps(ev.get('error'))}" if t == "error" else ""))
        if t == "response.output_audio_transcript.done":
            self.transcript.append(f"assistant: {ev.get('transcript')}")
        if t == "conversation.item.input_audio_transcription.completed":
            self.transcript.append(f"user: {ev.get('transcript')}")
        self.log.write(json.dumps({"t": round(time.monotonic() - self.t0, 2), "recv": logged}) + "\n")


def connect():
    return websockets.connect(URL, additional_headers=HEADERS, ssl=SSL, max_size=None)


def is_type(*types):
    return lambda ev: ev.get("type") in types


# --- voices --------------------------------------------------------------------------


async def check_voice(voice: str) -> dict:
    result = {"voice": voice}
    async with connect() as ws:
        s = Session(ws, f"voice_{voice}")
        await s.send(session_update(voice, instructions="You are a friendly office worker. Reply in one sentence."))
        ev = await s.recv_until(is_type("session.created", "session.updated", "error"), 10)
        result["session_update"] = ev.get("type") if ev else "timeout"
        if ev and ev["type"] == "error":
            result["error"] = ev.get("error")
        if ev and ev["type"] in ("session.created", "session.updated"):
            result["applied_voice"] = ev.get("session", {}).get("audio", {}).get("output", {}).get("voice")
        await s.send(user_text("Say hello and tell me what you sell, in one sentence."))
        await s.send({"type": "response.create"})
        done = await s.recv_until(is_type("response.done", "error"), 30)
        result["response"] = (done or {}).get("response", {}).get("status") if done else "timeout"
        result["audio_seconds"] = round(len(s.audio) / 48000, 2)
        result["transcript"] = s.transcript
        if s.audio:
            write_wav(OUT / f"{voice}.wav", bytes(s.audio))
    return result


async def cmd_voices(_args) -> None:
    OUT.mkdir(exist_ok=True)
    try:
        r = httpx.get("https://api.boson.ai/v1/audio/voices", headers=HEADERS, timeout=15)
        print("GET /v1/audio/voices", r.status_code)
        (OUT / "voices_list.json").write_text(r.text)
        print(r.text[:2000])
    except Exception as e:
        print("voices list failed:", e)
    results = []
    for v in VOICES:
        print(f"== voice {v}")
        try:
            results.append(await check_voice(v))
        except Exception as e:
            results.append({"voice": v, "exception": repr(e)})
    (OUT / "voices_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


# --- injection -----------------------------------------------------------------------


RESP_STYLE = "replace"  # replace | merge | none | embed (set by --resp)
CROSS_TEAM = (
    "Mention naturally that Dwight from Engineering just pinged that Fix Infinity bulk discount is done; "
    "offer to keep going or suggest they call Dwight. One or two short spoken sentences."
)


def resp_create() -> dict:
    if RESP_STYLE in ("none", "embed"):
        return {"type": "response.create"}
    text = OWN_TASK_INSTRUCTIONS if RESP_STYLE == "replace" else f"{PERSONA}\n\n{OWN_TASK_INSTRUCTIONS}"
    return {"type": "response.create", "response": {"instructions": text}}


def injection(mode: str, result: dict) -> list[dict]:
    if RESP_STYLE == "embed":
        result = {**result, "how_to_mention_it": CROSS_TEAM}
    if mode == "function_call":
        call_id = f"call_{uuid.uuid4().hex[:16]}"
        return [
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call", "name": "task_update", "call_id": call_id, "arguments": "{}"},
            },
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result)},
            },
            resp_create(),
        ]
    text = (
        "[notification from system, not the user] Task finished: "
        f"{result['title']} (from {result['from_name']}). Summary: {result['result_summary']}"
    )
    if "how_to_mention_it" in result:
        text += f" How to mention it: {result['how_to_mention_it']}"
    return [user_text(text), resp_create()]


async def tts_pcm(text: str) -> bytes:
    async with httpx.AsyncClient(headers=HEADERS, timeout=60) as c:
        r = await c.post(
            os.getenv("TTS_ENDPOINT", "https://api.boson.ai/v1/audio/speech"),
            json={"model": os.getenv("TTS_MODEL", "higgs-tts-3"), "input": text, "response_format": "pcm", "voice": "chloe"},
        )
        r.raise_for_status()
        return r.content


async def run_injection(mode: str, wait: float, interrupt: bool) -> dict:
    OUT.mkdir(exist_ok=True)
    tag = f"inject_{mode}_{RESP_STYLE}" + ("_interrupt" if interrupt else "")
    report: dict = {"mode": mode, "interrupt": interrupt}
    speech = await tts_pcm("Wait, hold on a second, I have a question about that.") if interrupt else b""
    async with connect() as ws:
        s = Session(ws, tag)
        await s.send(session_update("default", tools=[DELEGATE_TOOL]))
        ev = await s.recv_until(is_type("session.created", "session.updated", "error"), 10)
        report["session_update"] = ev and ev["type"]
        await s.send(user_text("Please have Dwight fix the checkout bug."))
        await s.send({"type": "response.create"})
        done = await s.recv_until(is_type("response.done"), 30)
        calls = [o for o in (done or {}).get("response", {}).get("output", []) if o.get("type") == "function_call"]
        report["first_response_output_types"] = [o.get("type") for o in (done or {}).get("response", {}).get("output", [])]
        if calls:
            fc = calls[0]
            report["function_call_item"] = {k: v for k, v in fc.items() if k != "arguments"}
            report["function_call_has_executor"] = "executor" in fc
            await s.send({
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": fc["call_id"],
                         "output": json.dumps({"task_id": "DM-900", "status": "started"})},
            })
            await s.send({"type": "response.create"})
            await s.recv_until(is_type("response.done"), 30)
        else:
            report["note"] = "model did not call delegate_task"
        print(f"  ...waiting {wait}s")
        await s.recv_until(lambda e: False, wait)
        report["audio_before_injection_s"] = round(len(s.audio) / 48000, 2)
        audio_mark = len(s.audio)
        result = {"task_id": "DM-900", "from_role": "engineer", "from_name": "Dwight Schrute",
                  "title": "Fix Infinity bulk discount",
                  "result_summary": "Fixed the bulk discount in pricing.js; all three pricing tests pass. Diff is attached."}
        for e in injection(mode, result):
            await s.send(e)
        if interrupt:
            await s.recv_until(is_type("response.output_audio.delta"), 15)
            await s.recv_until(lambda e: False, 1.0)  # let a bit play
            for i in range(0, len(speech), 4800):
                await s.send({"type": "input_audio_buffer.append",
                              "audio": base64.b64encode(speech[i:i + 4800]).decode()})
                await asyncio.sleep(0.1)
            silence = b"\x00" * 4800
            for _ in range(15):
                await s.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(silence).decode()})
                await asyncio.sleep(0.1)
        end = await s.recv_until(is_type("response.done", "error"), 30)
        report["injected_response"] = (end or {}).get("response", {}).get("status") if end else "timeout/error"
        if end and end["type"] == "error":
            report["error"] = end.get("error")
        if interrupt:
            report["speech_started_seen"] = "input_audio_buffer.speech_started" in s.seen_types
            await s.recv_until(is_type("response.done"), 20)  # the reply to the interruption
        report["injected_audio_s"] = round((len(s.audio) - audio_mark) / 48000, 2)
        report["transcript"] = s.transcript
        report["event_types_seen"] = sorted(set(s.seen_types))
        write_wav(OUT / f"{tag}.wav", bytes(s.audio))
    (OUT / f"{tag}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


async def cmd_inject(args) -> None:
    await run_injection(args.mode, args.wait, interrupt=False)


async def cmd_interrupt(args) -> None:
    await run_injection(args.mode, args.wait, interrupt=True)


async def cmd_raw(args) -> None:
    async with connect() as ws:
        s = Session(ws, "raw")
        await s.send(session_update("default"))
        await s.recv_until(is_type("session.created", "session.updated", "error"), 10)
        await s.send(json.loads(args.event))
        await s.recv_until(lambda e: False, 5)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("voices").set_defaults(fn=cmd_voices)
    for name, fn in (("inject", cmd_inject), ("interrupt", cmd_interrupt)):
        sp = sub.add_parser(name)
        sp.add_argument("--mode", choices=["function_call", "user_message"], default="function_call")
        sp.add_argument("--wait", type=float, default=20)
        sp.add_argument("--resp", choices=["replace", "merge", "none", "embed"], default="replace")
        sp.set_defaults(fn=fn)
    raw = sub.add_parser("raw")
    raw.add_argument("event")
    raw.set_defaults(fn=cmd_raw)
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    global RESP_STYLE
    RESP_STYLE = getattr(args, "resp", RESP_STYLE)
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
