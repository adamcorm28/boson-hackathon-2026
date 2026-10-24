"""Gateway routes for the frontend (spec §7a): /roles /board /tasks/{id} /events."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from company.types import CompanyUnavailable
from gateway import app_state, company_compat
from gateway.events import sse_stream

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
