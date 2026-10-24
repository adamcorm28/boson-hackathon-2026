"""Scripted stand-in for the browser: speaks TTS questions into WS /call/{role}.

Usage (gateway running on :8000, from backend/):
    .venv/bin/python dev/call_client.py ceo "How's the branch doing?"
    STAY=40 .venv/bin/python dev/call_client.py sales_lead "Hey Jim, how's the pipeline?"

Prints every JSON event and saves the assistant audio to spikes/out/call_<role>.wav.
dev/scenario.py drives `run_call` to rehearse the whole demo storyline.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path
from typing import Callable

import httpx
import websockets
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env")
GATEWAY_WS = os.getenv("GATEWAY_WS", "ws://localhost:8000")
TTS_CACHE = BACKEND / "data" / "tts_cache"
CHUNK = 24000 * 2 // 25  # 40 ms of PCM16 24 kHz


async def tts_pcm(text: str) -> bytes:
    """The 'user' saying `text` (cached, so reruns are fast)."""
    path = TTS_CACHE / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".pcm")
    if path.exists():
        return path.read_bytes()
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {os.environ['BOSON_API_KEY']}"}, timeout=60) as c:
        r = await c.post(os.getenv("TTS_ENDPOINT", "https://api.boson.ai/v1/audio/speech"),
                         json={"model": os.getenv("TTS_MODEL", "higgs-tts-3"), "input": text,
                               "response_format": "pcm", "voice": "chloe"})
        r.raise_for_status()
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


async def run_call(
    role: str,
    phrases: list[str],
    *,
    gateway: str = GATEWAY_WS,
    stay_seconds: float = 0,
    stop_when: Callable[[dict], bool] | None = None,
    verbose: bool = True,
    wav_path: Path | None = None,
) -> list[dict]:
    """Call `role`, say each phrase after the agent finishes its turn, optionally stay on the
    line (sending silence) for up to `stay_seconds` or until stop_when(event), then hang up.
    Returns every JSON event the gateway sent."""
    speech = [await tts_pcm(p) for p in phrases]
    audio = bytearray()
    events: list[dict] = []
    state = {"speaking": False, "last_quiet": time.monotonic(), "done": False, "bytes_since": 0, "stop": False}

    async with websockets.connect(f"{gateway}/call/{role}", max_size=None) as ws:
        async def reader():
            async for msg in ws:
                if isinstance(msg, bytes):
                    audio.extend(msg)
                    state["bytes_since"] += len(msg)
                    continue
                ev = json.loads(msg)
                events.append(ev)
                if verbose and ev["type"] not in ("transcript.assistant.delta", "agent.speaking"):
                    print("  <-", json.dumps(ev))
                if ev["type"] == "agent.speaking":
                    state["speaking"] = ev["value"]
                    if not ev["value"]:
                        state["last_quiet"] = time.monotonic()
                if stop_when and stop_when(ev):
                    state["stop"] = True
                if ev["type"] == "call.ended":
                    state["done"] = True
                    return

        async def wait_for_turn_end():
            # wait for the response to finish, then for its audio to "play" (it arrives faster than real time)
            while not state["done"] and (state["speaking"] or time.monotonic() - state["last_quiet"] < 1.0):
                await asyncio.sleep(0.1)
            await asyncio.sleep(state["bytes_since"] / 48000)
            state["bytes_since"] = 0

        async def silence(seconds: float):
            for _ in range(int(seconds * 25)):
                await ws.send(b"\x00" * CHUNK)
                await asyncio.sleep(0.04)

        read_task = asyncio.create_task(reader())
        await asyncio.sleep(1.0)
        await wait_for_turn_end()  # the greeting
        for phrase, pcm in zip(phrases, speech):
            if state["done"]:
                break
            if verbose:
                print(f"  -> (you say) {phrase}")
            for i in range(0, len(pcm), CHUNK):
                await ws.send(pcm[i:i + CHUNK])
                await asyncio.sleep(0.04)
            await silence(1.5)
            await asyncio.sleep(1.0)
            await wait_for_turn_end()
        if stay_seconds and verbose:
            print(f"  ... staying on the line (up to {stay_seconds:.0f}s)")
        end = time.monotonic() + stay_seconds
        while time.monotonic() < end and not state["done"] and not state["stop"]:
            await silence(0.5)
        if state["stop"]:
            await wait_for_turn_end()
        if not state["done"]:
            await ws.send(json.dumps({"type": "hangup"}))
        await asyncio.wait_for(read_task, 15)

    if wav_path:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(bytes(audio))
        if verbose:
            print(f"  saved {len(audio) / 48000:.1f}s of agent audio to {wav_path}")
    return events


if __name__ == "__main__":
    role, phrases = sys.argv[1], sys.argv[2:]
    asyncio.run(run_call(role, phrases, stay_seconds=float(os.getenv("STAY", "0")),
                         wav_path=BACKEND / "spikes" / "out" / f"call_{role}.wav"))
