"""Voice tool schemas (owned by A) and the router that runs them (spec §5.2, §5.3).

Tools never raise: any failure becomes {"error": "<sentence the model can say>"}.
"""

import logging
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

from company.types import ROLE_IDS, CompanyAPI, CompanyUnavailable, Issue
from gateway import company_compat
from gateway.roles import Role

log = logging.getLogger(__name__)

CLOSED_STATUSES = ("done", "cancelled")


def _fn(name: str, description: str, properties: dict | None = None) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": list(properties or {}),
        },
    }


_STR = {"type": "string"}

TOOL_SCHEMAS: dict[str, dict] = {
    "get_company_overview": _fn(
        "get_company_overview", "Branch KPIs, Q4 progress and issues flagged across all teams."),
    "read_inbox": _fn("read_inbox", "List the emails in your inbox (sender, subject, snippet)."),
    "read_email": _fn("read_email", "Read one email in full.", {"email_id": {**_STR, "description": "id from read_inbox"}}),
    "get_board": _fn("get_board", "The company task board: every task with its status and owner."),
    "get_issue": _fn("get_issue", "Details and comments for one task.", {"task_id": {**_STR, "description": "id from the board"}}),
    "get_my_work": _fn("get_my_work", "What you are working on right now: your status, latest progress note and open tasks."),
    "delegate_task": _fn(
        "delegate_task",
        "Hand off work to a teammate (or your own work body). Use it for anything that takes more than "
        "a few seconds: fixes, research, decks, spreadsheets, emails. Returns immediately; you get pinged when it's done.",
        {
            "assignee": {"type": "string", "enum": list(ROLE_IDS), "description": "role id of who does the work"},
            "title": {**_STR, "description": "short task title"},
            "brief": {**_STR, "description": "what to do and what done looks like"},
        },
    ),
    "get_financials": _fn("get_financials", "Branch P&L: monthly sales, margin and history."),
    "get_ai_spend": _fn("get_ai_spend", "What today's AI staff cost so far, in cents, total and by role."),
    "get_pipeline": _fn("get_pipeline", "The sales pipeline: accounts, value per year, stage, blockers."),
    "get_deal": _fn("get_deal", "One deal from the pipeline by account name.", {"name": {**_STR, "description": "account name or part of it"}}),
    "lookup_company": _fn(
        "lookup_company", "Search the company handbook (products, pricing, policies, org).",
        {"topic": {**_STR, "description": "what to look up"}}),
    "web_search": {"type": "web_search"},
}


@dataclass
class CallContext:
    role: Role
    company: CompanyAPI
    roles: dict[str, Role]
    on_task_started: Callable[[str, str, str], Awaitable[None]]  # (task_id, title, assignee_role)


def tools_for(role: Role) -> list[dict]:
    return [TOOL_SCHEMAS[name] for name in role.voice_tools]


def _name(ctx: CallContext, role_id: str | None) -> str | None:
    if role_id is None:
        return None
    role = ctx.roles.get(role_id)
    return role.name if role else role_id


def _card(ctx: CallContext, issue: Issue) -> dict:
    return {"task_id": issue.task_id, "title": issue.title, "status": issue.status,
            "assignee": _name(ctx, issue.assignee_role)}


async def _delegate(args: dict, ctx: CallContext) -> dict:
    assignee, title, brief = args.get("assignee"), args.get("title"), args.get("brief", "")
    if assignee not in ctx.role.can_delegate_to:
        allowed = ", ".join(_name(ctx, r) for r in ctx.role.can_delegate_to) or "nobody"
        return {"error": f"You can't assign work to {_name(ctx, assignee) or assignee}. You can delegate to: {allowed}."}
    if not title:
        return {"error": "The task needs a short title."}
    task_id = await ctx.company.create_task(assignee, title, brief, ctx.role.id)
    await ctx.on_task_started(task_id, title, assignee)
    return {"task_id": task_id, "status": "started", "assignee_name": _name(ctx, assignee), "eta_hint": "a few minutes"}


async def _dispatch(name: str, args: dict, ctx: CallContext) -> dict:
    dt = company_compat.data_tools()
    match name:
        case "get_company_overview":
            issues = await ctx.company.list_issues()
            flags = [_card(ctx, i) for i in issues if i.flagged and i.status not in CLOSED_STATUSES]
            return {**dt.company_overview(), "flags": flags}
        case "get_board":
            issues = await ctx.company.list_issues()
            return {"tasks": [_card(ctx, i) for i in issues if i.status != "cancelled"]}
        case "get_issue":
            i = await ctx.company.get_issue(args.get("task_id", ""))
            return {**_card(ctx, i), "description": i.description,
                    "requested_by": _name(ctx, i.requested_by_role),
                    "comments": [{"author": _name(ctx, c.author_role), "body": c.body} for c in i.comments[-5:]]}
        case "get_my_work":
            status = await ctx.company.get_agent_status(ctx.role.id)
            issues = await ctx.company.list_issues(role=ctx.role.id)
            return {"status": asdict(status),
                    "issues": [_card(ctx, i) for i in issues if i.status not in CLOSED_STATUSES]}
        case "delegate_task":
            return await _delegate(args, ctx)
        case "get_ai_spend":
            return await ctx.company.get_costs()
        case "get_financials":
            return dt.get_financials()
        case "get_pipeline":
            return {"deals": dt.get_pipeline()}
        case "get_deal":
            deal = dt.get_deal(args.get("name", ""))
            return deal if deal is not None else {"error": "I can't find that deal in the pipeline."}
        case "read_inbox":
            return {"emails": dt.read_inbox()}
        case "read_email":
            email = dt.read_email(args.get("email_id", ""))
            return email if email is not None else {"error": "I can't find that email."}
        case "lookup_company":
            return dt.lookup_company(args.get("topic", ""))
        case "web_search":
            return {"error": "Web search runs on the server, not here."}
    return {"error": f"I don't have a tool called {name}."}


async def run_tool(name: str, args: dict, ctx: CallContext) -> dict:
    if name not in TOOL_SCHEMAS:
        return {"error": f"I don't have a tool called {name}."}
    if name not in ctx.role.voice_tools:
        return {"error": f"That's not something I can do from here ({name})."}
    try:
        return await _dispatch(name, args or {}, ctx)
    except KeyError:
        return {"error": "I can't find that task on the board."}
    except CompanyUnavailable:
        return {"error": "The task board isn't responding right now."}
    except Exception:
        log.exception("tool %s failed", name)
        return {"error": "That didn't work, something went wrong on my end."}
