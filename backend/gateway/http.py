"""Gateway routes for the frontend (spec §7a): /roles /board /tasks/{id} /events /call/{role_id}."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from company.types import CompanyUnavailable, TaskResult
from gateway import app_state, company_compat
from gateway.call_session import CallSession
from gateway.events import sse_stream
from gateway.tools import CallContext

CLOSE_UNKNOWN_ROLE = 4404
CLOSE_ALREADY_ON_CALL = 4409

BOARD_COLUMNS = ("backlog", "todo", "in_progress", "in_review", "blocked", "done")

router = APIRouter()


@router.get("/roles")
async def get_roles():
    return [r.public() for r in app_state.roles.values()]


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
    session = CallSession(
        role, ws, app_state.connect_upstream, ctx, app_state.queue, app_state.bus,
        app_state.memory, mode=app_state.injection_mode,
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
