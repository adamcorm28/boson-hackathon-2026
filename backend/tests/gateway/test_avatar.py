import asyncio

from gateway import avatar
from gateway.avatar import AvatarStage, ClipStream, RenderFailed

PNG = b"\x89PNG\r\n\x1a\nfake"
ONE_SECOND = b"\x00\x00" * 24000


def stage(tmp_path, open_fn, sent, audio, clips):
    image = tmp_path / "ceo.png"
    image.write_bytes(PNG)

    async def emit(e):
        sent.append(e)

    async def emit_audio(pcm):
        audio.append(pcm)

    return AvatarStage(image, emit, emit_audio, "http://gw/", on_clip=clips.append, client=object(),
                       open_fn=open_fn)


def finished_clip(data: bytes = b"mp4") -> ClipStream:
    clip = ClipStream()
    clip.data += data
    clip.done = True
    clip.task = asyncio.get_running_loop().create_future()
    clip.task.set_result(None)
    avatar._clips[clip.id] = clip
    return clip


async def test_reply_goes_out_as_one_clip_after_its_text(tmp_path):
    sent, audio, clips = [], [], []

    async def open_fn(client, image_uri, pcm):
        assert image_uri.startswith("data:image/png;base64,")
        return finished_clip(b"mp4:" + pcm[:4])

    s = stage(tmp_path, open_fn, sent, audio, clips)
    s.feed_audio(ONE_SECOND)
    s.hold_event({"type": "transcript.assistant.done", "text": "Hi."})
    assert s.busy
    s.flush()
    await asyncio.gather(*s._tasks)
    assert [e["type"] for e in sent] == ["transcript.assistant.done", "avatar.clip"]
    assert sent[1]["url"].startswith("http://gw/avatar/clips/") and sent[1]["duration"] == 1.0
    clip = avatar.get_clip(sent[1]["url"].rsplit("/", 1)[1])
    assert b"".join([c async for c in clip.chunks()]) == b"mp4:" + ONE_SECOND[:4]
    assert clips == [1.0] and audio == [] and not s.busy


async def test_replies_keep_their_order(tmp_path):
    sent, audio, clips = [], [], []
    first_may_start = asyncio.Event()

    async def open_fn(client, image_uri, pcm):
        if len(pcm) > len(ONE_SECOND):
            await first_may_start.wait()
        return finished_clip()

    s = stage(tmp_path, open_fn, sent, audio, clips)
    s.feed_audio(ONE_SECOND * 2)
    s.hold_event({"type": "transcript.assistant.done", "text": "first"})
    s.flush()
    s.feed_audio(ONE_SECOND)
    s.hold_event({"type": "transcript.assistant.done", "text": "second"})
    s.flush()
    await asyncio.sleep(0.01)
    assert sent == []
    first_may_start.set()
    await asyncio.gather(*s._tasks)
    assert [e.get("text") or e["type"] for e in sent] == ["first", "avatar.clip", "second", "avatar.clip"]


async def test_failed_render_falls_back_to_plain_audio(tmp_path):
    sent, audio, clips = [], [], []

    async def open_fn(client, image_uri, pcm):
        raise RenderFailed("boom")

    s = stage(tmp_path, open_fn, sent, audio, clips)
    s.feed_audio(ONE_SECOND)
    s.flush()
    await asyncio.gather(*s._tasks)
    assert audio == [ONE_SECOND] and sent == [] and clips == [1.0]


async def test_cancel_drops_audio_but_keeps_the_text(tmp_path):
    sent, audio, clips = [], [], []
    never = asyncio.Event()

    async def open_fn(client, image_uri, pcm):
        await never.wait()

    s = stage(tmp_path, open_fn, sent, audio, clips)
    s.feed_audio(ONE_SECOND)
    s.hold_event({"type": "transcript.assistant.done", "text": "rendering"})
    s.flush()
    s.feed_audio(ONE_SECOND)
    s.hold_event({"type": "transcript.assistant.delta", "text": "held"})
    await asyncio.sleep(0.01)
    await s.cancel()
    assert [e["text"] for e in sent] == ["rendering", "held"]
    assert audio == [] and clips == [] and not s.busy


async def test_clip_stream_readers_follow_along_until_done():
    clip = ClipStream()
    await clip.append(b"moov")
    got = []

    async def read():
        async for chunk in clip.chunks():
            got.append(chunk)

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.01)
    await clip.append(b"moof")
    await clip.finish()
    await reader
    assert b"".join(got) == b"moovmoof"


def test_ref_image_path_finds_any_supported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar, "AVATARS_DIR", tmp_path)
    assert avatar.ref_image_path("cfo") is None
    (tmp_path / "cfo.webp").write_bytes(b"x")
    assert avatar.ref_image_path("cfo") == tmp_path / "cfo.webp"
