"""Scripted stand-in for the browser: speaks TTS questions into WS /call/{role} (Checkpoint 1).

Usage (gateway running on :8000, from backend/):
    .venv/bin/python spikes/call_client.py ceo "How's the branch doing?"
    .venv/bin/python spikes/call_client.py eng_lead "What happened with Infinity?" "Have Dwight fix it."

Prints every JSON event and saves the assistant audio to spikes/out/call_<role>.wav.
"""

import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE.parent / ".env")
GATEWAY = os.getenv("GATEWAY_WS", "ws://localhost:8000")
CHUNK = 24000 * 2 // 25  # 40 ms of PCM16 24 kHz


async def tts_pcm(text: str) -> bytes:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {os.environ['BOSON_API_KEY']}"}, timeout=60) as c:
        r = await c.post(os.getenv("TTS_ENDPOINT", "https://api.boson.ai/v1/audio/speech"),
                         json={"model": os.getenv("TTS_MODEL", "higgs-tts-3"), "input": text,
                               "response_format": "pcm", "voice": "chloe"})
        r.raise_for_status()
        return r.content


async def main(role: str, phrases: list[str]) -> None:
    speech = [await tts_pcm(p) for p in phrases]
    audio = bytearray()
    state = {"speaking": False, "last_quiet": time.monotonic(), "done": False, "bytes_since": 0}

    async with websockets.connect(f"{GATEWAY}/call/{role}", max_size=None) as ws:
        async def reader():
            async for msg in ws:
                if isinstance(msg, bytes):
                    audio.extend(msg)
                    state["bytes_since"] += len(msg)
                    continue
                ev = json.loads(msg)
                if ev["type"] != "transcript.assistant.delta":
                    print("  <-", json.dumps(ev))
                if ev["type"] == "agent.speaking":
                    state["speaking"] = ev["value"]
                    if not ev["value"]:
                        state["last_quiet"] = time.monotonic()
                if ev["type"] == "call.ended":
                    state["done"] = True
                    return

        async def wait_for_turn_end():
            # wait for a response to finish, plus its (faster than real time) audio to "play"
            while state["speaking"] or time.monotonic() - state["last_quiet"] < 1.0:
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
            print(f"  -> (speaking) {phrase}")
            for i in range(0, len(pcm), CHUNK):
                await ws.send(pcm[i:i + CHUNK])
                await asyncio.sleep(0.04)
            await silence(1.5)
            await asyncio.sleep(1.0)
            await wait_for_turn_end()
        wait_extra = float(os.getenv("WAIT_AFTER", "0"))
        if wait_extra:
            print(f"  ... staying on the line {wait_extra}s")
            end = time.monotonic() + wait_extra
            while time.monotonic() < end and not state["done"]:
                await silence(1.0)
        if not state["done"]:
            await ws.send(json.dumps({"type": "hangup"}))
        await asyncio.wait_for(read_task, 15)

    out = HERE / "out" / f"call_{role}.wav"
    out.parent.mkdir(exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(bytes(audio))
    print(f"saved {len(audio) / 48000:.1f}s of assistant audio to {out}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
