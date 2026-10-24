"""Session instructions: persona + speaking style + tool rules + live briefing (spec §5.1)."""

from gateway.company_compat import parse_result
from company.types import CompanyAPI, CompanyUnavailable, TaskResult
from gateway.roles import Role

UNAVAILABLE = "(task board unavailable right now)"

SPEAKING_STYLE = """\
## Speaking style
- You are on a live phone call: short spoken sentences.
- Please never read out IDs or URLs; say the task's name instead.
- Stay in character, with at most one comedy bit per reply.
- Every number comes from a tool or the briefing below. Never make one up."""

TOOL_RULES = """\
## Tools
- Questions about our own business (how the branch or sales are doing, our numbers, the board, your inbox, \
our deals and money, what someone is working on) always start with a tool call. Never answer them from memory, \
not even roughly.
- Questions about the outside world (competitors, their financials, the market, industry tools and trends, \
news, best practices) or that need real, in-depth analysis go to research: call it, say you're digging in, \
and keep talking. Never answer those with our own company numbers, and don't guess.
- When research results come back, share the headline and offer to go through them; get_issue on that task \
gives the full findings.
- Use delegate_task for anything that takes more than a few seconds: fixes, research, decks, spreadsheets, emails.
- When the user asks for work to be done, call delegate_task first. Never say it's handled, or that someone \
is on it, unless delegate_task returned "started".
- Until the user asks for the work, recommend what you'd do and ask if they want it; don't claim anyone is on it.
- Short go-aheads count: "do it", "go ahead", "have Dwight fix it", "get someone on it" all mean \
call delegate_task right now, in this reply, with a clear title and brief.
- After delegating, say who's on it and keep the conversation going. Don't wait for the result.
- When a task_update arrives, or a message marked [notification from system, not the user], mention it briefly, \
then let the user steer.
- If a tool returns an error, say so plainly in one sentence."""


async def build_briefing(
    role: Role,
    company: CompanyAPI,
    recent_calls: list[str],
    pending: list[TaskResult],
    roles: dict[str, Role],
) -> str:
    def name(role_id: str | None) -> str:
        return roles[role_id].name if role_id in roles else (role_id or "someone")

    sections = ["# Live briefing"]
    try:
        issues = await company.list_issues()
    except CompanyUnavailable:
        issues = None

    open_issues = [] if issues is None else [i for i in issues if i.status not in ("done", "cancelled")]
    own = [i for i in open_issues if i.assignee_role == role.id]
    if issues is None:
        lines = [UNAVAILABLE]
    else:
        lines = [f"- {i.title} ({i.status.replace('_', ' ')}, id {i.task_id})" for i in own] or ["- nothing open"]
    sections.append("## Your open work\n" + "\n".join(lines))

    if role.reports_to is None:  # the CEO sees flags across all teams
        if issues is None:
            lines = [UNAVAILABLE]
        else:
            flagged = [i for i in open_issues if i.flagged]
            lines = [f"- {i.title} ({name(i.assignee_role)}, {i.status.replace('_', ' ')})" for i in flagged] or ["- none"]
        sections.append("## Flagged across the company\n" + "\n".join(lines))

    if role.can_delegate_to:
        lines = [f"- {name(r)}: assignee \"{r}\"" + (" (your own work body, for slow work you do yourself)" if r == role.id else "")
                 for r in role.can_delegate_to]
        sections.append("## Who you can hand work to with delegate_task\n" + "\n".join(lines))

    if recent_calls:
        sections.append(
            "## Your recent calls with the user\n"
            "(Notes only. Work counts as delegated only if it's in your open work or on the board.)\n"
            + "\n".join(f"- {c}" for c in recent_calls[:3]))

    if issues is not None:
        done_research = [i for i in issues if i.assignee_role == role.id and i.kind == "research" and i.status == "done"][-3:]
        lines = []
        for i in done_research:
            try:
                parsed = parse_result((await company.get_issue(i.task_id)).comments)
            except (KeyError, CompanyUnavailable):
                parsed = None
            if parsed:
                lines.append(f"- {i.title} (id {i.task_id}): {parsed[0]}")
        if lines:
            sections.append("## Research you finished recently (get_issue gives the full findings)\n" + "\n".join(lines))

    if pending:
        lines = [f"- {r.title}, from {name(r.from_role)}: {r.summary}" for r in pending]
        sections.append("## Finished results you haven't told the user about\n" + "\n".join(lines))

    return "\n\n".join(sections)


def build_instructions(role: Role, briefing: str) -> str:
    # The greeting lives here, not on the first response.create: per-response instructions
    # make Higgs Realtime ignore tools later in the call (see realtime-findings.md).
    call_start = f"## Call start\nThe user just called you. {greeting_instructions(role)}"
    return "\n\n".join([role.persona.strip(), SPEAKING_STYLE, TOOL_RULES, briefing, call_start])


def greeting_instructions(role: Role) -> str:
    return f"Answer the call in character with: {role.greeting}"
