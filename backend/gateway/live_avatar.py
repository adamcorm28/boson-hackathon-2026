"""Live lip-synced avatar for a call: Boson's realtime avatar session in a LiveKit Cloud room.

The gateway still owns the Higgs Realtime session. Instead of sending the agent's PCM to the
browser, it streams it to a Boson avatar over a LiveKit data stream; the avatar publishes
lip-synced video plus that same audio into the room, and the browser plays both from there.
See docs.boson.ai/models/higgs-avatar/realtime-sessions.

Faces: Boson presets (builtin_claire_v1, builtin_emma_v1, builtin_james_v1) or avatars Boson has
registered on this API key, mapped per role in backend/data/live_avatars.yaml ({role_id: avatar_id}).
Needs LIVEKIT_URL (wss://<project>.livekit.cloud), LIVEKIT_API_KEY and LIVEKIT_API_SECRET.
"""

import asyncio
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import yaml

log = logging.getLogger(__name__)

AVATARS_FILE = Path(os.getenv("LIVE_AVATARS", Path(__file__).parent.parent / "data" / "live_avatars.yaml"))
SESSIONS_URL = os.getenv("AVATAR_SESSIONS_ENDPOINT", "https://api.boson.ai/v1/avatar/sessions")
AGENT_IDENTITY = "gateway"  # streams the agent's speech; the avatar only accepts audio from it
AVATAR_IDENTITY = "boson-avatar"
VIEWER_IDENTITY = "viewer"
SAMPLE_RATE = 24000
MAX_DURATION_S = int(os.getenv("LIVE_AVATAR_MAX_SECONDS", "900"))
START_TIMEOUT_S = 30
# Avatar slots are shared by every Boson user; when all are busy, keep trying this long before the
# call falls back to plain audio. The greeting waits meanwhile, so keep it short: long enough for the
# previous call's slot to free up on back-to-back calls, not a long silence when Boson is full.
BUSY_RETRY_S = float(os.getenv("LIVE_AVATAR_BUSY_RETRY_SECONDS", "5"))
_FLUSH = object()  # queue marker: end of one reply


def configured() -> bool:
    return all(os.getenv(k) for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))


def avatar_id_for(role_id: str) -> str | None:
    """The Boson avatar for this role, or None (no live avatar: plain voice)."""
    if not configured() or not AVATARS_FILE.exists():
        return None
    mapping = yaml.safe_load(AVATARS_FILE.read_text()) or {}
    value = mapping.get(role_id)
    return str(value) if value else None


def _token(room: str, identity: str, *, publish: bool, subscribe: bool, on_behalf: str | None = None) -> str:
    from livekit import api  # imported lazily: the gateway runs without LiveKit installed

    grants = api.VideoGrants(
        room_join=True, room=room, can_publish=publish, can_subscribe=subscribe, can_publish_data=True,
        can_publish_sources=["camera", "microphone"] if publish else None,
    )
    token = (api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
             .with_identity(identity).with_grants(grants).with_ttl(timedelta(seconds=MAX_DURATION_S + 300)))
    if on_behalf:
        token = token.with_kind("agent").with_attributes({"lk.publish_on_behalf": on_behalf})
    return token.to_jwt()


class LiveAvatar:
    """One call's avatar. push() and friends never block; a sender task feeds the avatar in order."""

    def __init__(self, avatar_id: str):
        self.avatar_id = avatar_id
        self.room_name = f"dm-call-{uuid.uuid4().hex[:12]}"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {os.environ.get('BOSON_API_KEY', '')}"}, timeout=60)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._room = None
        self._output = None
        self._session_id: str | None = None
        self._sender: asyncio.Task | None = None

    async def join(self) -> dict:
        """Join the room and return what the browser needs to watch it. The browser can join while
        summon() is still putting the avatar in, which saves a round of waiting."""
        from livekit import rtc

        url = os.environ["LIVEKIT_URL"]
        async with asyncio.timeout(START_TIMEOUT_S):
            self._room = rtc.Room()
            await self._room.connect(url, _token(self.room_name, AGENT_IDENTITY, publish=True, subscribe=True),
                                     options=rtc.RoomOptions(auto_subscribe=False))
        return {
            "url": url,
            "token": _token(self.room_name, VIEWER_IDENTITY, publish=False, subscribe=True),
            "avatar_identity": AVATAR_IDENTITY,
        }

    async def summon(self) -> None:
        """Put the avatar in the joined room and start feeding it the agent's speech."""
        from livekit import rtc
        from livekit.agents.voice.avatar import DataStreamAudioOutput

        url = os.environ["LIVEKIT_URL"]
        async with asyncio.timeout(START_TIMEOUT_S):
            body = {
                "avatar_id": self.avatar_id,
                "transport": {
                    "type": "livekit",
                    "url": url,
                    "room_name": self.room_name,
                    "participant_token": _token(self.room_name, AVATAR_IDENTITY, publish=True, subscribe=False,
                                                on_behalf=AGENT_IDENTITY),
                    "participant_identity": AVATAR_IDENTITY,
                    "publisher_identity": AGENT_IDENTITY,
                },
                "max_duration_seconds": MAX_DURATION_S,
            }
            give_up = asyncio.get_running_loop().time() + BUSY_RETRY_S
            while True:
                resp = await self._client.post(SESSIONS_URL, json=body)
                busy = resp.status_code in (429, 503) and "insufficient_quota" not in resp.text
                if not busy or asyncio.get_running_loop().time() >= give_up:
                    break
                wait = min(float(resp.headers.get("Retry-After") or 2), 3.0)
                log.info("avatar slots busy (%s); retrying in %.1fs", resp.status_code, wait)
                await asyncio.sleep(wait)
            if resp.is_error:
                raise RuntimeError(f"avatar session: {resp.status_code} {resp.text[:300]}")
            self._session_id = resp.json()["id"]
        self._output = DataStreamAudioOutput(self._room, destination_identity=AVATAR_IDENTITY,
                                             sample_rate=SAMPLE_RATE, wait_remote_track=rtc.TrackKind.KIND_AUDIO)
        self._sender = asyncio.create_task(self._send_loop())
        log.info("live avatar %s in room %s (session %s)", self.avatar_id, self.room_name, self._session_id)

    def push(self, pcm: bytes) -> None:
        self._queue.put_nowait(pcm)

    def end_reply(self) -> None:
        self._queue.put_nowait(_FLUSH)

    def interrupt(self) -> None:
        """Barge-in: drop queued speech and tell the avatar to stop what it's playing."""
        self.drain()
        if self._output is not None:
            self._output.clear_buffer()

    def drain(self) -> list[bytes]:
        """Take the speech not yet sent (e.g. to play it as plain audio when summon() failed)."""
        out = []
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item is not _FLUSH:
                out.append(item)
        return out

    async def _send_loop(self) -> None:
        from livekit import rtc

        while True:
            item = await self._queue.get()
            if item is _FLUSH:
                self._output.flush()
            elif len(item) >= 2:
                pcm = item[: len(item) // 2 * 2]
                await self._output.capture_frame(rtc.AudioFrame(pcm, SAMPLE_RATE, 1, len(pcm) // 2))

    async def close(self) -> None:
        if self._sender is not None:
            self._sender.cancel()
            await asyncio.gather(self._sender, return_exceptions=True)
        if self._session_id is not None:
            try:
                await self._client.delete(f"{SESSIONS_URL}/{self._session_id}")
            except httpx.HTTPError as e:
                log.warning("releasing avatar session %s failed: %s", self._session_id, e)
        if self._room is not None:
            try:
                await self._room.disconnect()
            except Exception:
                pass
        await self._client.aclose()
