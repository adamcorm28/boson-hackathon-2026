"""Gateway routes for the frontend (spec §7a): /roles /board /tasks/{id} /events /call/{role_id}."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from company.types import CompanyUnavailable, TaskResult
from gateway import app_state, avatar, company_compat, live_avatar
from gateway.call_session import CallSession
from gateway.events import sse_stream
from gateway.tools import CallContext

CLOSE_UNKNOWN_ROLE = 4404
CLOSE_ALREADY_ON_CALL = 4409

BOARD_COLUMNS = ("backlog", "todo", "in_progress", "in_review", "blocked", "done")

router = APIRouter()


@router.get("/roles")
async def get_roles():
    return [r.public() | _avatar_urls(r.id) | {"avatar_live": live_avatar.avatar_id_for(r.id) is not None}
            for r in app_state.roles.values()]


@router.get("/roles/{role_id}/status")
async def get_role_status(role_id: str):
    """What someone is doing right now, for the frontend's contact profile: idle or working, the
    current task, and the latest note on it (the company layer's get_agent_status)."""
    if role_id not in app_state.roles:
        raise HTTPException(404, f"Unknown role {role_id}")
    try:
        status = await app_state.company.get_agent_status(role_id)
    except CompanyUnavailable:
        raise HTTPException(503, "Company backend unavailable")
    return asdict(status)


def _avatar_urls(role_id: str) -> dict:
    """The still face and the muted talking loop for a role with a reference image (gateway/avatar.py).
    In sync mode there's no loop: replies arrive as lip-synced clips on the call socket."""
    image = avatar.ref_image_path(role_id) if avatar.enabled() else None
    if image is None:
        return {"avatar_url": None, "avatar_loop_url": None, "avatar_idle_url": None}
    base = app_state.PUBLIC_URL.rstrip("/")
    version = f"?v={image.stat().st_mtime_ns}"  # a replaced image gets a new URL, so no stale cached face
    loop = None if avatar.sync_mode() else f"{base}/avatar/loops/{role_id}{version}"
    return {"avatar_url": f"{base}/avatar/images/{role_id}{version}", "avatar_loop_url": loop,
            "avatar_idle_url": f"{base}/avatar/idle/{role_id}{version}"}


@router.get("/avatar/images/{role_id}")
async def get_avatar_image(role_id: str):
    path = avatar.ref_image_path(role_id)
    if path is None:
        raise HTTPException(404, f"No avatar image for {role_id}")
    return FileResponse(path)


@router.get("/avatar/loops/{role_id}")
async def get_avatar_loop(role_id: str):
    try:
        path = await avatar.talking_loop(role_id)
    except Exception as e:
        raise HTTPException(502, f"Couldn't render the talking loop: {e}")
    if path is None:
        raise HTTPException(404, f"No avatar image for {role_id}")
    return FileResponse(path, media_type="video/mp4")


@router.get("/avatar/idle/{role_id}")
async def get_avatar_idle(role_id: str):
    try:
        path = await avatar.idle_loop(role_id)
    except Exception as e:
        raise HTTPException(502, f"Couldn't render the idle loop: {e}")
    if path is None:
        raise HTTPException(404, f"No avatar image for {role_id}")
    return FileResponse(path, media_type="video/mp4")


@router.get("/avatar/clips/{clip_id}")
async def get_avatar_clip(clip_id: str):
    clip = avatar.get_clip(clip_id)
    if clip is None:
        raise HTTPException(404, "Unknown or expired clip")
    # Relayed while Boson is still rendering it (fragmented MP4), so playback starts early.
    return StreamingResponse(clip.chunks(), media_type="video/mp4", headers={"Cache-Control": "no-store"})


@router.get("/board")
async def get_board():
    try:
        issues = await app_state.company.list_issues()
    except CompanyUnavailable:
        raise HTTPException(503, "Company backend unavailable")
    columns: dict[str, list] = {s: [] for s in BOARD_COLUMNS}
    for i in issues:
        if i.status in columns:
            columns[i.status].append({
                "task_id": i.task_id, "title": i.title, "assignee_role": i.assignee_role,
                "status": i.status, "origin": i.origin,
            })
    return {"columns": columns}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        issue = await app_state.company.get_issue(task_id)
    except KeyError:
        raise HTTPException(404, f"Unknown task {task_id}")
    except CompanyUnavailable:
        raise HTTPException(503, "Company backend unavailable")
    parsed = company_compat.parse_result(issue.comments)
    summary, artifacts = parsed if parsed else (None, [])
    return {
        "task_id": issue.task_id,
        "title": issue.title,
        "assignee_role": issue.assignee_role,
        "status": issue.status,
        "result_summary": summary,
        "artifacts": [asdict(a) for a in artifacts],
    }


@router.get("/events")
async def events():
    return StreamingResponse(
        sse_stream(app_state.bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/call/{role_id}")
async def call(ws: WebSocket, role_id: str):
    await ws.accept()  # accept first so the browser sees our close code
    role = app_state.roles.get(role_id)
    if role is None:
        await ws.close(code=CLOSE_UNKNOWN_ROLE)
        return
    if app_state.active_call is not None:
        await ws.close(code=CLOSE_ALREADY_ON_CALL)
        return
    ctx = CallContext(role=role, company=app_state.company, roles=app_state.roles, on_task_started=None)
    # ?video=1: a video call with the role's Boson live avatar; otherwise voice only, as fast as before.
    video = ws.query_params.get("video") == "1"
    live_id = live_avatar.avatar_id_for(role.id) if video else None
    session = CallSession(
        role, ws, app_state.connect_upstream, ctx, app_state.queue, app_state.bus,
        app_state.memory, mode=app_state.injection_mode,
        avatar_image=(avatar.ref_image_path(role.id) if video and avatar.enabled() and avatar.sync_mode() and not live_id
                      else None),
        public_url=app_state.PUBLIC_URL,
        live_avatar=live_avatar.LiveAvatar(live_id) if live_id else None,
    )
    app_state.active_call = session
    try:
        await session.run()
    finally:
        app_state.active_call = None
        try:
            await ws.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # already closed by the browser


@router.post("/dev/complete/{task_id}")
async def dev_complete(task_id: str, summary: str = "Done. All tests pass."):
    """Mock company only: finish a task as if its agent posted RESULT, to rehearse pings."""
    complete = getattr(app_state.company, "complete", None)
    if complete is None:
        raise HTTPException(404, "Only available with COMPANY_BACKEND=mock")
    try:
        issue = await app_state.company.get_issue(task_id)
    except KeyError:
        raise HTTPException(404, f"Unknown task {task_id}")
    complete(task_id, summary)
    if app_state.watcher is None:  # no watcher yet (B9): announce directly
        await app_state.on_complete(TaskResult(
            task_id=task_id, title=issue.title, from_role=issue.assignee_role or "",
            requested_by_role=issue.requested_by_role, summary=summary,
        ))
    return {"ok": True}
