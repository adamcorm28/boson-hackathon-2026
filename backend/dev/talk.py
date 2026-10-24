"""Call an agent yourself from the terminal: your mic in, their voice out.

Usage (gateway running on :8000, from backend/):
    .venv/bin/pip install -r requirements-dev.txt     # once (adds sounddevice)
    .venv/bin/python dev/talk.py eng_lead
    .venv/bin/python dev/talk.py sales_lead --full-duplex   # with headphones: lets you interrupt

Roles: ceo (Michael), cfo (Kevin), eng_lead (Ryan), engineer (Dwight), sales_lead (Jim).
Ctrl+C hangs up. Transcripts, tool calls and live task-board events print as they happen.

Without headphones the agent hears itself through your mic, so by default the mic is
muted while the agent is talking (half duplex). Use --full-duplex with headphones.
"""

import argparse
import asyncio
import json
import signal
import threading
import time

import httpx
import sounddevice as sd
import websockets

RATE = 24000
BLOCK = 960  # 40 ms
SILENCE = b"\x00" * BLOCK * 2


class Player:
    """Plays PCM16 chunks as they arrive; clear() stops playback instantly (barge-in)."""

    def __init__(self):
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.last_audio = 0.0

    def callback(self, outdata, frames, time_info, status):
        n = len(outdata)
        with self.lock:
            chunk = bytes(self.buf[:n])
            del self.buf[:n]
        if chunk:
            self.last_audio = time.monotonic()
        outdata[:] = chunk + b"\x00" * (n - len(chunk))

    def enqueue(self, pcm: bytes) -> None:
        with self.lock:
            self.buf.extend(pcm)

    def clear(self) -> None:
        with self.lock:
            self.buf.clear()

    @property
    def playing(self) -> bool:
        with self.lock:
            pending = len(self.buf)
        return pending > 0 or time.monotonic() - self.last_audio < 0.4


async def print_board_events(http_url: str, names: dict[str, str]) -> None:
    def who(role):
        return names.get(role, role or "?")

    try:
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{http_url}/events") as resp:
                type_ = None
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        type_ = line[7:]
                    elif line.startswith("data: ") and type_:
                        d = json.loads(line[6:])
                        if type_ == "task.updated":
                            print(f"   [board] {d['title']} -> {d['status']} ({who(d.get('assignee_role'))})")
                        elif type_ == "task.completed":
                            print(f"   [done]  {who(d['from_role'])} finished \"{d['title']}\": {d['summary']}")
                        elif type_ == "ping":
                            target = who(d["to_role"]) if d["to_role"] else "nobody on a call"
                            print(f"   [ping]  {d['text']} (announced to {target})")
                        elif type_ == "agent.status" and d["state"] == "working":
                            print(f"   [desk]  {who(d['role'])} is working")
    except (httpx.HTTPError, asyncio.CancelledError):
        pass


async def main(role: str, gateway: str, full_duplex: bool) -> None:
    http_url = gateway.replace("ws://", "http://").replace("wss://", "https://")
    roles = httpx.get(f"{http_url}/roles", timeout=5).json()
    names = {r["id"]: r["name"] for r in roles}
    if role not in names:
        raise SystemExit(f"Unknown role {role!r}. Try one of: {', '.join(names)}")
    name = names[role]

    loop = asyncio.get_running_loop()
    mic_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
    player = Player()
    hangup = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, hangup.set)

    def on_mic(indata, frames, time_info, status):
        data = bytes(indata)
        loop.call_soon_threadsafe(lambda: mic_q.full() or mic_q.put_nowait(data))

    board = asyncio.create_task(print_board_events(http_url, names))
    print(f"Calling {name}... (Ctrl+C to hang up{'' if full_duplex else '; mic mutes while they talk'})")
    if full_duplex:
        print("  --full-duplex needs headphones: through speakers the agent hears itself and keeps cutting off.\n"
              "  (The browser frontend has echo cancellation built in; this terminal tool doesn't.)")
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK, callback=on_mic), \
         sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK, callback=player.callback):
        async with websockets.connect(f"{gateway}/call/{role}", max_size=None) as ws:

            async def send_mic():
                while True:
                    frame = await mic_q.get()
                    if not full_duplex and player.playing:
                        frame = SILENCE  # keep the stream steady, but don't let them hear themselves
                    await ws.send(frame)

            async def receive():
                try:
                    await handle(ws)
                except websockets.ConnectionClosed as e:
                    code = e.rcvd.code if e.rcvd else None
                    print("-- someone else is already on a call" if code == 4409 else f"-- disconnected ({code})")

            async def handle(ws):
                async for msg in ws:
                    if isinstance(msg, bytes):
                        player.enqueue(msg)
                        continue
                    ev = json.loads(msg)
                    t = ev["type"]
                    if t == "transcript.assistant.done":
                        print(f"{name}: {ev['text']}")
                    elif t == "transcript.user":
                        print(f"you: {ev['text']}")
                    elif t == "tool.called":
                        print(f"   [tool]  {ev['name']}({json.dumps(ev['args'])})")
                    elif t == "task.started":
                        print(f"   [task]  started \"{ev['title']}\" -> {names.get(ev['assignee_role'], ev['assignee_role'])}")
                    elif t == "barge_in":
                        player.clear()
                    elif t == "call.ended":
                        print(f"-- call ended ({ev['reason']})")
                        return

            async def wait_hangup():
                await hangup.wait()
                await ws.send(json.dumps({"type": "hangup"}))
                await asyncio.sleep(5)  # give the gateway time to send call.ended

            tasks = [asyncio.create_task(c) for c in (send_mic(), receive(), wait_hangup())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception() and not isinstance(t.exception(), websockets.ConnectionClosed):
                    raise t.exception()
    await asyncio.sleep(1.0)  # let any board events from the hang-up print
    board.cancel()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("role")
    p.add_argument("--gateway", default="ws://localhost:8000")
    p.add_argument("--full-duplex", action="store_true", help="don't mute the mic while the agent talks (use headphones)")
    a = p.parse_args()
    try:
        asyncio.run(main(a.role, a.gateway, a.full_duplex))
    except websockets.InvalidStatus as e:
        raise SystemExit(f"Gateway refused the call: {e}")
