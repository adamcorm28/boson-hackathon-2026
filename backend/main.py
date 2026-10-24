"""FastAPI backend exposing the three Boson AI models.

- Higgs Realtime (speech-to-speech over WebSocket)
- Higgs TTS 3 (text-to-speech)
- Higgs Avatar (talking-head video)

Run with:  uvicorn main:app --reload
"""

import asyncio
import os
import ssl
from typing import Literal, Optional

import certifi
import httpx
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load backend/.env regardless of the directory uvicorn is started from.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Imported after load_dotenv: the gateway reads COMPANY_BACKEND / ROLES_DIR at import.
from gateway import http as gateway_http  # noqa: E402

BOSON_API_KEY = os.environ["BOSON_API_KEY"]

REALTIME_MODEL = os.getenv("REALTIME_MODEL", "higgs-realtime")
REALTIME_ENDPOINT = os.getenv("REALTIME_ENDPOINT", "wss://api.boson.ai/v1/realtime")
TTS_MODEL = os.getenv("TTS_MODEL", "higgs-tts-3")
TTS_ENDPOINT = os.getenv("TTS_ENDPOINT", "https://api.boson.ai/v1/audio/speech")
AVATAR_MODEL = os.getenv("AVATAR_MODEL", "higgs-avatar")
AVATAR_VIDEO_ENDPOINT = os.getenv("AVATAR_VIDEO_ENDPOINT", "https://api.boson.ai/v1/videos")
AVATAR_STREAM_ENDPOINT = os.getenv("AVATAR_STREAM_ENDPOINT", "https://api.boson.ai/v1/videos/stream")

REALTIME_URL = f"{REALTIME_ENDPOINT}?model={REALTIME_MODEL}"
# Client secrets are minted over REST at <realtime endpoint>/client_secrets.
REALTIME_CLIENT_SECRETS_URL = REALTIME_ENDPOINT.replace("wss://", "https://", 1) + "/client_secrets"
AUTH_HEADERS = {"Authorization": f"Bearer {BOSON_API_KEY}"}
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

app = FastAPI(title="Boson Hackathon Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Video-Id"],
)

# Voice gateway: /roles /board /tasks /events /call/{role_id}, plus agent artifacts.
app.include_router(gateway_http.router)
ARTIFACTS_DIR = os.getenv(
    "ARTIFACTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")

client = httpx.AsyncClient(headers=AUTH_HEADERS, timeout=120)


@app.on_event("shutdown")
async def close_client():
    await client.aclose()


def raise_for_boson_error(resp: httpx.Response):
    if resp.is_error:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)


async def stream_from_boson(url: str, body: dict, media_type: str) -> StreamingResponse:
    """Open a streaming POST to Boson and relay the bytes to the caller."""
    req = client.build_request("POST", url, json=body)
    resp = await client.send(req, stream=True)
    if resp.is_error:
        await resp.aread()
        await resp.aclose()
        raise_for_boson_error(resp)

    async def body_iter():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()

    headers = {}
    if "x-video-id" in resp.headers:
        headers["X-Video-Id"] = resp.headers["x-video-id"]
    return StreamingResponse(body_iter(), media_type=media_type, headers=headers)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Higgs TTS 3 — POST TTS_ENDPOINT
# ---------------------------------------------------------------------------

AudioFormat = Literal["mp3", "opus", "pcm", "wav", "aac", "flac"]

AUDIO_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "pcm": "audio/pcm",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "flac": "audio/flac",
}


class SpeechRequest(BaseModel):
    input: str
    model: str = TTS_MODEL
    voice: Optional[str] = None
    response_format: AudioFormat = "mp3"
    stream: bool = False
    ref_audio: Optional[str] = None  # URL, data URI, or base64 audio for voice cloning
    ref_text: Optional[str] = None
    normalize: Optional[bool] = None
    language: Optional[str] = None  # ISO 639-3
    timestamps: Optional[bool] = None


@app.post("/tts")
async def text_to_speech(req: SpeechRequest):
    """Synthesize speech. Returns audio bytes, a raw 16-bit/24kHz/mono PCM stream
    when `stream` is true, or JSON (base64 audio + word timings) when `timestamps` is true."""
    body = req.model_dump(exclude_none=True)

    if req.stream:
        if req.response_format != "pcm":
            raise HTTPException(400, "Streaming requires response_format='pcm'")
        return await stream_from_boson(TTS_ENDPOINT, body, "audio/pcm")

    resp = await client.post(TTS_ENDPOINT, json=body)
    raise_for_boson_error(resp)
    if req.timestamps:
        return resp.json()
    return Response(content=resp.content, media_type=AUDIO_MEDIA_TYPES[req.response_format])


# ---------------------------------------------------------------------------
# Higgs Avatar — AVATAR_VIDEO_ENDPOINT / AVATAR_STREAM_ENDPOINT
# ---------------------------------------------------------------------------


class AvatarTTSInput(BaseModel):
    """Text-to-video driving input (same body as /tts, minus `stream`)."""

    input: str
    model: str = TTS_MODEL
    voice: Optional[str] = None
    ref_audio: Optional[str] = None
    ref_text: Optional[str] = None
    normalize: Optional[bool] = None
    language: Optional[str] = None


class VideoRequest(BaseModel):
    ref_image: str  # URL, data URI, or base64 image (PNG/JPEG/WEBP)
    input: Optional[str] = None  # driving audio: URL, data URI, or base64 (max 60s)
    input_tts: Optional[AvatarTTSInput] = None
    size: Literal["640x640", "640x480", "480x640"] = "640x640"
    model: str = AVATAR_MODEL


def video_body(req: VideoRequest) -> dict:
    if (req.input is None) == (req.input_tts is None):
        raise HTTPException(400, "Provide exactly one of `input` or `input_tts`")
    return req.model_dump(exclude_none=True)


@app.post("/avatar/videos")
async def create_video(req: VideoRequest):
    """Start an async avatar video job. Poll GET /avatar/videos/{id} for status."""
    resp = await client.post(AVATAR_VIDEO_ENDPOINT, json=video_body(req))
    raise_for_boson_error(resp)
    return resp.json()


@app.get("/avatar/videos/{video_id}")
async def get_video(video_id: str):
    """Job status: queued | in_progress | completed | failed."""
    resp = await client.get(f"{AVATAR_VIDEO_ENDPOINT}/{video_id}")
    raise_for_boson_error(resp)
    return resp.json()


@app.get("/avatar/videos/{video_id}/content")
async def get_video_content(video_id: str):
    """Download the rendered MP4 once the job is completed."""
    resp = await client.get(f"{AVATAR_VIDEO_ENDPOINT}/{video_id}/content")
    raise_for_boson_error(resp)
    return Response(content=resp.content, media_type="video/mp4")


@app.post("/avatar/videos/stream")
async def stream_video(req: VideoRequest):
    """Stream fragmented MP4 as it's generated. The video id is in the X-Video-Id header."""
    return await stream_from_boson(AVATAR_STREAM_ENDPOINT, video_body(req), "video/mp4")


# ---------------------------------------------------------------------------
# Higgs Realtime — REALTIME_ENDPOINT (WebSocket)
# ---------------------------------------------------------------------------


class ClientSecretRequest(BaseModel):
    expires_in_seconds: int = 600


@app.post("/realtime/client-secret")
async def create_realtime_client_secret(req: ClientSecretRequest = ClientSecretRequest()):
    """Mint a short-lived ephemeral key so a browser can connect to Boson directly:
    new WebSocket("wss://api.boson.ai/v1/realtime?model=higgs-realtime",
                  ["realtime", `bai-client-secret.${value}`])"""
    resp = await client.post(
        REALTIME_CLIENT_SECRETS_URL,
        json={"expires_after": {"seconds": req.expires_in_seconds}},
    )
    raise_for_boson_error(resp)
    return resp.json()


@app.websocket("/realtime")
async def realtime_proxy(ws: WebSocket):
    """Relay a client WebSocket to Higgs Realtime, injecting the API key server-side.
    Clients speak the OpenAI-compatible Realtime protocol (session.update,
    input_audio_buffer.append, response.create, ...) exactly as they would upstream."""
    await ws.accept()
    try:
        async with websockets.connect(
            REALTIME_URL,
            additional_headers=AUTH_HEADERS,
            ssl=SSL_CONTEXT,
            max_size=None,
        ) as upstream:

            async def client_to_boson():
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        return
                    if msg.get("text") is not None:
                        await upstream.send(msg["text"])
                    elif msg.get("bytes") is not None:
                        await upstream.send(msg["bytes"])

            async def boson_to_client():
                async for msg in upstream:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        await ws.send_text(msg)

            tasks = [
                asyncio.create_task(client_to_boson()),
                asyncio.create_task(boson_to_client()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                    raise t.exception()
    except WebSocketDisconnect:
        pass
    except websockets.ConnectionClosed as e:
        await ws.close(code=e.rcvd.code if e.rcvd else 1011)
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass
