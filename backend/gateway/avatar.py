"""Higgs Avatar faces for calls (stretch goal; spec §likeness: drawn or preset faces only).

A role with a reference image in backend/data/avatars/<role_id>.(png|jpg|jpeg|webp) (gitignored,
per machine) gets a face. Boson's live avatar sessions only take its registered faces (see
gateway/live_avatar.py, which wins when a role has one), so there are two modes (AVATAR_MODE):
- "loop": the voice stays live. A muted talking clip, rendered once per image with
  POST /v1/videos and cached, loops while the agent speaks. Lips move with speech, not word for word.
- "sync" (default): each reply's audio is held back and rendered with POST /v1/videos/stream; the gateway
  relays the fragmented MP4 (video plus that same audio) to the browser as Boson generates it,
  faster than real time. Lips match exactly; the voice starts ~2 s after the reply's audio is in.
In both modes a muted idle loop (the face listening: blinks, small head moves; rendered once per
image from silence and played forward then backward so it loops without a jump) runs underneath,
so the face never freezes between replies.
Renders run one at a time because Boson rate-limits a second concurrent job.
"""

import asyncio
import base64
import io
import logging
import os
import shutil
import subprocess
import uuid
import wave
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

AVATARS_DIR = Path(os.getenv("AVATARS_DIR", Path(__file__).parent.parent / "data" / "avatars"))
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
VIDEOS_URL = os.getenv("AVATAR_VIDEO_ENDPOINT", "https://api.boson.ai/v1/videos")
STREAM_URL = os.getenv("AVATAR_STREAM_ENDPOINT", "https://api.boson.ai/v1/videos/stream")
MODEL = os.getenv("AVATAR_MODEL", "higgs-avatar")
SIZE = os.getenv("AVATAR_SIZE", "640x640")  # 640x640, 480x640 or 640x480; match the images' aspect
SAMPLE_RATE = 24000
PCM_BYTES_PER_S = SAMPLE_RATE * 2
MAX_CLIP_S = 55  # the API takes up to 60 s of driving audio
POLL_S = 0.3
RENDER_TIMEOUT_S = 90
RATE_LIMIT_RETRIES = 8
KEEP_CLIPS = 30

_render_lock = asyncio.Lock()  # one job at a time across calls: a second concurrent job gets a 429
_clips: OrderedDict[str, "ClipStream"] = OrderedDict()


LOOP_DIR = AVATARS_DIR / "cache"
# Driving speech for the talking loop: varied mouth shapes, no long pauses (about 8 s).
LOOP_TEXT = ("Okay, here's where we are. The numbers look good, the team is on it, and I'll have "
             "the full update for you shortly. Anything else you need from me today?")
TTS_MODEL = os.getenv("TTS_MODEL", "higgs-tts-3")
IDLE_SECONDS = 6
LOOP_KINDS = ("talk", "idle")


def enabled() -> bool:
    """AVATAR_CALLS=0 turns faces off (plain voice and pixel portraits) without moving the images."""
    return os.getenv("AVATAR_CALLS", "1") != "0"


def sync_mode() -> bool:
    return os.getenv("AVATAR_MODE", "sync") == "sync"


def ref_image_path(role_id: str) -> Path | None:
    for ext in IMAGE_TYPES:
        path = AVATARS_DIR / f"{role_id}{ext}"
        if path.exists():
            return path
    return None


def get_clip(clip_id: str) -> "ClipStream | None":
    return _clips.get(clip_id)


class ClipStream:
    """One reply's lip-synced MP4, kept in memory as Boson streams it; readers replay it from the
    start and then follow along until it's complete."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.data = bytearray()
        self.done = False
        self.task: asyncio.Task | None = None
        self._cond = asyncio.Condition()

    async def append(self, chunk: bytes) -> None:
        async with self._cond:
            self.data += chunk
            self._cond.notify_all()

    async def finish(self) -> None:
        async with self._cond:
            self.done = True
            self._cond.notify_all()

    def cancel(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()

    async def chunks(self):
        pos = 0
        while True:
            async with self._cond:
                await self._cond.wait_for(lambda: pos < len(self.data) or self.done)
                chunk = bytes(self.data[pos:])
                finished = self.done
            if chunk:
                pos += len(chunk)
                yield chunk
            elif finished:
                return


async def open_stream(client: httpx.AsyncClient, image_uri: str, pcm: bytes) -> ClipStream:
    """Start rendering this audio as a streamed clip; returns once the first bytes are in, so a
    failure before then can still fall back to plain audio."""
    body = {"model": MODEL, "size": SIZE, "ref_image": image_uri, "input": _data_uri("audio/wav", _wav(pcm))}
    clip = ClipStream()
    first: asyncio.Future = asyncio.get_running_loop().create_future()
    clip.task = asyncio.create_task(_pump(client, body, clip, first))
    try:
        await first
    except BaseException:
        clip.cancel()
        raise
    _clips[clip.id] = clip
    while len(_clips) > KEEP_CLIPS:
        _clips.popitem(last=False)
    return clip


async def _pump(client: httpx.AsyncClient, body: dict, clip: ClipStream, first: asyncio.Future) -> None:
    try:
        async with _render_lock, asyncio.timeout(RENDER_TIMEOUT_S):
            for attempt in range(RATE_LIMIT_RETRIES):
                async with client.stream("POST", STREAM_URL, json=body) as resp:
                    if resp.status_code == 429:
                        await resp.aread()
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    if resp.is_error:
                        raise RenderFailed(f"stream: {resp.status_code} {(await resp.aread())[:200]!r}")
                    async for chunk in resp.aiter_bytes():
                        await clip.append(chunk)
                        if not first.done():
                            first.set_result(None)
                    break
            else:
                raise RenderFailed("stream: still rate-limited")
        if not first.done():
            raise RenderFailed("stream: empty response")
    except BaseException as e:
        if not first.done():
            first.set_exception(e if isinstance(e, Exception) else RenderFailed("cancelled"))
        elif not isinstance(e, asyncio.CancelledError):
            log.warning("avatar stream %s broke off: %r", clip.id, e)
        if isinstance(e, asyncio.CancelledError):
            raise
    finally:
        await clip.finish()


def _wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _data_uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


class RenderFailed(Exception):
    pass


async def render(client: httpx.AsyncClient, image_uri: str, pcm: bytes) -> bytes:
    """One clip: the MP4 for this audio, lip-synced to the reference image."""
    return await _render_body(client, {"ref_image": image_uri, "input": _data_uri("audio/wav", _wav(pcm))})


async def _render_body(client: httpx.AsyncClient, body: dict) -> bytes:
    body = {"model": MODEL, "size": SIZE} | body
    async with _render_lock:
        for attempt in range(RATE_LIMIT_RETRIES):
            resp = await client.post(VIDEOS_URL, json=body)
            if resp.status_code != 429:
                break
            await asyncio.sleep(0.5 * (attempt + 1))
        if resp.is_error:
            raise RenderFailed(f"create: {resp.status_code} {resp.text[:200]}")
        video_id = resp.json()["id"]
        async with asyncio.timeout(RENDER_TIMEOUT_S):
            while True:
                await asyncio.sleep(POLL_S)
                status = (await client.get(f"{VIDEOS_URL}/{video_id}")).json()
                if status.get("status") == "completed":
                    break
                if status.get("status") == "failed":
                    raise RenderFailed(f"{video_id} failed: {status.get('error')}")
        content = await client.get(f"{VIDEOS_URL}/{video_id}/content")
        if content.is_error:
            raise RenderFailed(f"download: {content.status_code}")
        return content.content


Emit = Callable[[dict], Awaitable[None]]
EmitAudio = Callable[[bytes], Awaitable[None]]


def _boson_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"Authorization": f"Bearer {os.environ.get('BOSON_API_KEY', '')}"}, timeout=60)


def _loop_path(image: Path, kind: str) -> Path:
    return LOOP_DIR / f"{image.stem}-{kind}-{image.stat().st_mtime_ns}.mp4"  # a new image gets new loops


_loop_jobs: dict[Path, asyncio.Task] = {}


async def talking_loop(role_id: str) -> Path | None:
    """The role's cached talking clip, rendered on first use (~10 s); None without an image."""
    return await _cached_loop(role_id, "talk")


async def idle_loop(role_id: str) -> Path | None:
    """The role's cached listening clip (seamless), rendered on first use (~8 s); None without an image."""
    return await _cached_loop(role_id, "idle")


async def _cached_loop(role_id: str, kind: str) -> Path | None:
    image = ref_image_path(role_id)
    if image is None:
        return None
    path = _loop_path(image, kind)
    if path.exists():
        return path
    if path not in _loop_jobs:
        _loop_jobs[path] = asyncio.create_task(_render_loop(image, path, kind))
    try:
        return await asyncio.shield(_loop_jobs[path])
    finally:
        if _loop_jobs.get(path) is not None and _loop_jobs[path].done():
            _loop_jobs.pop(path, None)


async def _render_loop(image: Path, path: Path, kind: str) -> Path:
    driver = ({"input_tts": {"model": TTS_MODEL, "input": LOOP_TEXT, "voice": "default"}} if kind == "talk"
              else {"input": _data_uri("audio/wav", _wav(b"\x00\x00" * SAMPLE_RATE * IDLE_SECONDS))})
    async with _boson_client() as client:
        mp4 = await _render_body(client, {"ref_image": _data_uri(IMAGE_TYPES[image.suffix.lower()], image.read_bytes())}
                                 | driver)
    path.parent.mkdir(parents=True, exist_ok=True)
    for old in path.parent.glob(f"{image.stem}-{kind}-*.mp4"):
        old.unlink()
    tmp = path.with_suffix(".part")
    tmp.write_bytes(mp4)
    if kind == "idle":
        await asyncio.to_thread(_ping_pong, tmp)
    tmp.rename(path)  # atomic: a request never serves a half-written file
    log.info("rendered %s loop %s", kind, path.name)
    return path


def _ping_pong(path: Path) -> None:
    """Forward then backward, silent: the last frame meets the first, so looping shows no jump.
    Without ffmpeg the plain clip is kept (a small jump each loop)."""
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg not found; the idle loop will jump when it repeats")
        return
    out = path.with_name(path.stem + "-pp.mp4")
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-filter_complex", "[0:v]reverse[r];[0:v][r]concat=n=2:v=1[v]",
         "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("idle ping-pong failed, keeping the plain clip: %s", result.stderr[-300:])
        return
    out.replace(path)


async def prepare_loops(role_ids, kinds: tuple[str, ...] = LOOP_KINDS) -> None:
    """Startup: render missing loops in the background so the first call doesn't wait."""
    for role_id in role_ids:
        for kind in kinds:
            try:
                await _cached_loop(role_id, kind)
            except Exception as e:
                log.warning("%s loop for %s failed: %s", kind, role_id, e)


class AvatarStage:
    """Holds one call's agent audio and client transcript events per reply, renders each reply,
    and emits it in order: the reply's transcript events, then an `avatar.clip` event. If a render
    fails, the reply's raw PCM goes out instead so the user still hears it."""

    def __init__(self, image_path: Path, emit: Emit, emit_audio: EmitAudio, public_url: str,
                 on_clip: Callable[[float], None], client: httpx.AsyncClient | None = None,
                 open_fn: Callable[[httpx.AsyncClient, str, bytes], Awaitable[ClipStream]] = open_stream):
        self._image_uri = _data_uri(IMAGE_TYPES[image_path.suffix.lower()], image_path.read_bytes())
        self._emit = emit
        self._emit_audio = emit_audio
        self._public_url = public_url.rstrip("/")
        self._on_clip = on_clip  # (clip seconds) when a clip goes out, so the injector waits for it
        self._client = client or _boson_client()
        self._open = open_fn
        self._streams: set[ClipStream] = set()  # still rendering: stopped on barge-in
        self._pcm = bytearray()
        self._events: list[dict] = []
        self._tasks: set[asyncio.Task] = set()
        self._previous: asyncio.Task | None = None  # replies go out in order

    @property
    def busy(self) -> bool:
        """A reply is still held back or rendering."""
        return bool(self._pcm) or bool(self._tasks)

    def feed_audio(self, pcm: bytes) -> None:
        self._pcm += pcm

    def hold_event(self, event: dict) -> None:
        self._events.append(event)

    def flush(self) -> None:
        """The reply is complete: render it and send it after any earlier reply."""
        pcm, events = bytes(self._pcm), self._events
        self._pcm, self._events = bytearray(), []
        if not pcm and not events:
            return
        task = asyncio.create_task(self._deliver(pcm, events, self._previous))
        self._previous = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cancel(self) -> None:
        """Barge-in: drop held and rendering replies. Their text still goes out so the transcript
        shows what the agent said, but nothing plays."""
        events = [e for t in self._tasks for e in getattr(t, "held_events", [])] + self._events
        self._pcm, self._events = bytearray(), []
        for t in list(self._tasks):
            t.cancel()
        for clip in self._streams:
            clip.cancel()  # frees the render slot for the next reply
        self._streams.clear()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._previous = None
        for e in events:
            await self._emit(e)

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        for clip in self._streams:
            clip.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._client.aclose()

    async def _deliver(self, pcm: bytes, events: list[dict], previous: asyncio.Task | None) -> None:
        asyncio.current_task().held_events = events  # for cancel()
        if previous is not None:
            await asyncio.gather(previous, return_exceptions=True)
        step = MAX_CLIP_S * PCM_BYTES_PER_S
        for i in range(0, max(len(pcm), 1), step):
            part = pcm[i:i + step]
            clip = None
            if part:
                try:
                    clip = await self._open(self._client, self._image_uri, part)
                except (RenderFailed, httpx.HTTPError, TimeoutError, KeyError, ValueError) as e:
                    log.warning("avatar render failed, sending plain audio: %s", e)
            if i == 0:  # the reply's words appear as it starts playing
                asyncio.current_task().held_events = []
                for e in events:
                    await self._emit(e)
            if not part:
                continue
            seconds = len(part) / PCM_BYTES_PER_S
            self._on_clip(seconds)
            if clip is None:
                await self._emit_audio(part)
            else:
                self._streams.add(clip)
                clip.task.add_done_callback(lambda _t, c=clip: self._streams.discard(c))
                url = f"{self._public_url}/avatar/clips/{clip.id}"
                await self._emit({"type": "avatar.clip", "url": url, "duration": round(seconds, 2)})
