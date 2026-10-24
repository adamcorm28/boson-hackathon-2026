# Voice Gateway Implementation Plan (Workstream A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI gateway where the browser calls one Dunder Mifflin employee at a time. Each employee is a Higgs Realtime voice agent that knows the company's live state, uses fast tools, delegates slow work, and announces finished work (its own or a teammate's) without cutting anyone off.

**Architecture:**
- The gateway owns the Higgs Realtime WebSocket. For each call, a `CallSession` connects the browser socket to Boson, builds the session from the role YAML and a live briefing, runs tool calls through `CompanyAPI`, and injects completed-task notices when both sides are quiet.
- An `EventBus` fans events out to SSE for the frontend.
- B's `TaskWatcher` feeds completions into the bus and into the active call.

**Tech Stack:** Python 3.11+, FastAPI, `websockets>=13`, httpx, pyyaml, anthropic, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-23-voice-company-design.md`. **Index / shared contracts:** `docs/superpowers/plans/2026-10-23-voice-company-index.md`

## Global Constraints

- Upstream is `wss://api.boson.ai/v1/realtime?model=higgs-realtime`, using `Authorization: Bearer $BOSON_API_KEY` (reuse `AUTH_HEADERS` and `SSL_CONTEXT` from `backend/main.py`). Audio is PCM16 24 kHz mono, base64 in JSON.
- `output_modalities` is exactly `["audio"]`. Turn detection is `server_vad` with defaults unless the role overrides it. Input transcription is `{"model": "higgs-stt-3.1"}`.
- Insertable message roles are only `user`/`assistant`. With `server_vad`, `response.create` interrupts an in-flight response, so **never send `response.create` while `response_active` is true**, except as the immediate continuation after a client tool's output.
- `web_search` is declared as `{"type": "web_search"}`. Don't answer `executor: "server"` calls; only handle `function_call` items with `executor == "client"` (or no executor).
- Injection gate: `response_active` and `user_speaking` are both false, **and** ≥ 1.5 s have passed since the later of `response.done` and `speech_stopped`.
- Instructions must include the persona, "short spoken sentences; never read out IDs or URLs", the live briefing, and the tool rules.
- The frontend contract is exactly spec §7a plus the index's additions (close code `4409`, ping semantics).
- Call summaries use model `claude-haiku-5-5` and fall back to the last 6 transcript lines.

## Review Focus

- **The user starts talking during the 1.5 s quiet window, or while the injected reply is being created:** the next `speech_started` cancels the attempt, and the notice is re-queued if `response.created` hasn't arrived for it yet. Test it in A6.
- **The model calls `delegate_task` for a role outside `can_delegate_to`, or an unknown tool:** return `{"error": "..."}` as the output so the model says so; never raise. Test it in A3.
- **The browser disconnects mid-response or mid-tool call:** upstream closes, the call is saved, `agent.status` goes back to idle, and there's no traceback loop. Test it in A7.
- **Upstream closes with `session.idle_timeout` or `max_duration_reached`, or code 1013/4429:** send `call.ended {reason}` to the browser and close cleanly. Test it in A7.
- **Several completions queue up during one call:** announce one per quiet gap, oldest first, never two back to back without a user turn in between. Test it in A6.

## File Structure

```
backend/
  main.py                    # modify: include gateway router, startup/shutdown hooks
  gateway/
    __init__.py
    roles.py                 # Role, load_roles
    tools.py                 # TOOL_SCHEMAS, tools_for, run_tool, CallContext
    instructions.py          # build_briefing, build_instructions
    events.py                # EventBus
    injector.py              # TurnState, NotificationQueue, injection_events
    memory.py                # CallRecord, CallMemory, summarize
    call_session.py          # CallSession
    http.py                  # APIRouter: /roles /board /tasks /events /call/{role_id} /artifacts
    app_state.py             # singletons: bus, memory, queue, active call, watcher wiring
  spikes/realtime_spike.py   # throwaway
  tests/gateway/ test_roles.py test_tools.py test_instructions.py test_events.py test_injector.py test_memory.py test_call_session.py test_http.py
docs/superpowers/spikes/realtime-findings.md
```

---

### Task A1: Spikes S1 + S2, voices and injection (throwaway, no TDD, do it first)

**Files:**
- Create: `backend/spikes/realtime_spike.py`, `docs/superpowers/spikes/realtime-findings.md`

- [ ] **Step 1: Voice check.** For each of `default, marcus, jake, oliver, chloe, eleanor, nora`:
  - open a session, send `session.update` with that voice
  - record whether `session.updated` or `error` comes back
  - send a text `user` message, then `response.create`
  - save `response.output_audio.delta` to `spikes/out/<voice>.wav`
  
  Also run `GET https://api.boson.ai/v1/audio/voices` and list any other presets. Listen to each file.
- [ ] **Step 2: Injection check.**
  1. Open a session with a `delegate_task` function tool. Send the user text "Please have Dwight fix the checkout bug", then `response.create`.
  2. On the `function_call`, reply with `function_call_output` `{"task_id": "DM-900", "status": "started"}`, then `response.create`.
  3. Wait 20 s, then inject using **mode `function_call`**: a synthetic `function_call` item named `task_update` with a new `call_id`, then `function_call_output`, then `response.create` with the spec §5.4 own-task instructions.
  4. Save the audio and transcript.
  5. Repeat with **mode `user_message`** (the `[notification from system, not the user] …` text).
- [ ] **Step 3: Interruption check.** While the injected reply is playing, send `input_audio_buffer.append` with 1 s of recorded speech. Confirm `speech_started` arrives and the response ends `cancelled`.
- [ ] **Step 4:** Write `realtime-findings.md`:
  - which voices are accepted, and the voice picked for Kevin
  - which injection mode works and sounds natural; set `INJECTION_MODE` in `.env` and tell B and C
  - event names actually observed, including whether the `function_call` item carries an `executor` field
  - any error codes seen
- [ ] **Step 5:** Commit `docs: realtime spike findings` (the spike script too).

### Task A2: Role loading and `GET /roles`

**Files:**
- Create: `backend/gateway/{__init__,roles}.py`, `backend/tests/gateway/test_roles.py`

**Interfaces:**
- Produces `@dataclass Role` with these fields:
  - `id, name, title, reports_to: str | None, paperclip_agent, voice, greeting, persona`
  - `voice_tools: list[str]`, `can_delegate_to: list[str]`
  - `turn_detection: dict | None`, `sprite: str | None`, `desk: str | None`
- `load_roles(roles_dir: Path = Path(__file__).parent.parent / "roles") -> dict[str, Role]` raises `ValueError` naming the file on a missing required key or an unknown tool (checked against `VOICE_TOOL_NAMES`).
- `Role.public() -> dict` returns the §7a `/roles` shape: `id, name, title, reports_to, voice, sprite, desk`.

- [ ] **Step 1: Write failing tests** using `tmp_path` YAML fixtures. Don't depend on B3's files.
  - `test_load_valid_role`
  - `test_missing_key_raises_with_filename`
  - `test_unknown_tool_raises`
  - `test_public_shape`: the keys are exactly the §7a set.
- [ ] **Step 2:** Run `cd backend && pytest tests/gateway/test_roles.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gateway): role loader`.

### Task A3: Tool schemas and router

**Files:**
- Create: `backend/gateway/tools.py`, `backend/tests/gateway/test_tools.py`

**Interfaces:**
- Consumes `CompanyAPI`, `data_tools` and `VOICE_TOOL_NAMES` (shared contract 1), plus `Role`.
- Produces:
  - `TOOL_SCHEMAS: dict[str, dict]`: one OpenAI-style `{"type": "function", "name", "description", "parameters"}` per name in `VOICE_TOOL_NAMES`, except that `web_search` maps to `{"type": "web_search"}`.
  - `tools_for(role: Role) -> list[dict]`
  - `@dataclass CallContext`: `role: Role`, `company: CompanyAPI`, `roles: dict[str, Role]`, `on_task_started: Callable[[str, str, str], Awaitable[None]]` with args `(task_id, title, assignee_role)`
  - `async run_tool(name: str, args: dict, ctx: CallContext) -> dict`
- Parameters:
  - `get_issue {task_id}`
  - `read_email {email_id}`
  - `get_deal {name}`
  - `lookup_company {topic}`
  - `delegate_task {assignee: enum(role ids), title, brief}`; the description says "for anything that takes more than a few seconds: fixes, research, decks, spreadsheets, emails"
  - everything else takes no parameters
- Behavior:
  - `get_board` returns compact `[{task_id, title, status, assignee}]`, with `assignee` as the character name.
  - `get_my_work` returns `{status: AgentStatus fields, issues: [...]}` for `ctx.role.id`.
  - `get_company_overview` returns `data_tools.company_overview()` plus `"flags": [flagged non-done issues]`.
  - `get_ai_spend` returns `get_costs()`.
  - `delegate_task`: checks `assignee in role.can_delegate_to`, calls `create_task(assignee, title, brief, role.id)`, awaits `on_task_started`, and returns `{"task_id", "status": "started", "assignee_name", "eta_hint": "a few minutes"}`.
  - Errors: a tool not in `role.voice_tools`, a disallowed assignee, `KeyError` or `CompanyUnavailable` all return `{"error": "<short sentence the model can say>"}`.

- [ ] **Step 1: Write failing tests** with `MockCompany`:
  - `test_schemas_cover_all_tool_names`: `set(TOOL_SCHEMAS) == VOICE_TOOL_NAMES`.
  - `test_tools_for_web_search_is_server_tool`
  - `test_delegate_creates_voice_task_and_notifies`: eng_lead → engineer; `on_task_started` is called once; the issue's `requested_by_role == "eng_lead"`.
  - `test_delegate_disallowed_assignee_returns_error`: engineer → sales_lead.
  - `test_tool_not_in_role_returns_error`
  - `test_get_issue_unknown_returns_error`
  - `test_overview_includes_flags`: the bulk-discount issue is in `flags`.
- [ ] **Step 2:** Run `pytest tests/gateway/test_tools.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gateway): voice tool schemas and router`.

### Task A4: Briefing and instruction builder

**Files:**
- Create: `backend/gateway/instructions.py`, `backend/tests/gateway/test_instructions.py`

**Interfaces:**
- `async build_briefing(role: Role, company: CompanyAPI, recent_calls: list[str], pending: list[TaskResult], roles: dict[str, Role]) -> str`. It produces Markdown sections:
  - "Your open work": the role's non-done issues, as title, status and ID
  - "Flagged across the company": CEO only, flagged issues
  - "Your recent calls with the user": up to 3 lines
  - "Finished results you haven't told the user about"
- `build_instructions(role: Role, briefing: str) -> str` produces: the persona, then a **Speaking style** section, then a **Tools** section, then the briefing.
  - **Speaking style:** "short spoken sentences; never read out IDs or URLs; at most one comedy bit per reply; every number comes from a tool or the briefing"
  - **Tools:** "use delegate_task for anything that takes more than a few seconds; after delegating, say you're on it and keep the conversation going; when a task_update arrives, mention it briefly"
- `greeting_instructions(role) -> str` produces: "Answer the call in character with: {greeting}".

- [ ] **Step 1: Write failing tests:**
  - `test_instructions_contain_persona_and_rules`: assert the substrings `"never read out IDs or URLs"`, `"at most one comedy bit"` and `"delegate_task"`.
  - `test_briefing_lists_own_open_issues_only`: eng_lead sees the bulk-discount issue but not the CFO's.
  - `test_ceo_briefing_has_flags`
  - `test_briefing_includes_pending_results`: a `TaskResult` titled "Fix bulk discount" appears.
  - `test_briefing_survives_company_unavailable`: the section says "(task board unavailable right now)".
- [ ] **Step 2:** Run `pytest tests/gateway/test_instructions.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gateway): persona and live briefing instructions`.

### Task A5: EventBus, SSE and REST endpoints

**Files:**
- Create: `backend/gateway/{events,http,app_state}.py`, `backend/tests/gateway/{test_events,test_http}.py`
- Modify: `backend/main.py` to `app.include_router(gateway.http.router)` and mount `StaticFiles` at `/artifacts` from `ARTIFACTS_DIR`. Keep the existing endpoints.

**Interfaces:**
- `EventBus`:
  - `publish(type: str, data: dict) -> None` (synchronous, non-blocking)
  - `subscribe() -> AsyncIterator[tuple[str, dict]]`
  - each subscriber gets its own `asyncio.Queue(maxsize=100)`; if it overflows, drop the oldest event
- `app_state.py` holds the module singletons: `bus`, `roles`, `company` (from `get_company()`), `memory`, `queue`, and `active_call: CallSession | None`.
- Routes:
  - `GET /roles` → `[Role.public()]`
  - `GET /board` → the §7a `columns` shape, with every status key present even when empty
  - `GET /tasks/{task_id}` → §7a, with `result_summary`/`artifacts` from `results.parse_result`; 404 on `KeyError`
  - `GET /events` → SSE (`event:`/`data:` frames, plus a `: keepalive` comment every 15 s)

- [ ] **Step 1: Write failing tests:**
  - `test_bus_fanout_two_subscribers`
  - `test_bus_slow_subscriber_drops_oldest`
  - `test_get_roles` (with FastAPI `TestClient`)
  - `test_board_has_all_columns`
  - `test_task_404`
  - `test_task_result_parsed`: after `MockCompany.complete(...)` with an `ARTIFACT:` line, the response has one artifact.
- [ ] **Step 2:** Run `pytest tests/gateway/test_events.py tests/gateway/test_http.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS. Then run `uvicorn main:app` and `curl -N localhost:8000/events` and check that keepalives arrive.
- [ ] **Step 5:** Commit `feat(gateway): event bus, SSE and board/task endpoints`.

### Task A6: Turn state, notification queue and injection events

**Files:**
- Create: `backend/gateway/injector.py`, `backend/tests/gateway/test_injector.py`

**Interfaces:**
- `TurnState`:
  - `on_upstream(event_type: str, now: float)` tracks `response.created/done` and `input_audio_buffer.speech_started/stopped`
  - `ready(now: float) -> bool`
  - `mark_injected(now)`: blocks further injections until the user has spoken at least once since the last one (the "never two back to back" rule)
- `NotificationQueue`:
  - `push(result: TaskResult)`, `pop() -> TaskResult | None`, `requeue_front(result)`, `pending() -> list[TaskResult]`
  - FIFO. A `task_id` already queued is ignored.
- `injection_events(result: TaskResult, active_role: Role, roles: dict[str, Role], mode: Literal["function_call", "user_message"]) -> list[dict]` returns the exact client events from spec §5.4:
  - **mode `function_call`:** the `function_call` item named `task_update` with a fresh `call_id`, then `function_call_output` with `{task_id, from_role, from_name, title, result_summary}`, then `response.create` with instructions
  - **mode `user_message`:** one `user` `input_text` message starting `"[notification from system, not the user]"`, then `response.create`
  - **instructions:** if `result.requested_by_role == active_role.id` or `result.from_role == active_role.id`, use the own-task text; otherwise the cross-team text, with `{name}` = the from-role character and `{team}` from its title

- [ ] **Step 1: Write failing tests:**
  - `test_not_ready_while_response_active`
  - `test_not_ready_while_user_speaking`
  - `test_ready_after_1_5s_quiet`: `speech_stopped` at t=10, so `ready(11.4)` is False and `ready(11.6)` is True.
  - `test_not_ready_twice_without_user_turn`
  - `test_queue_fifo_and_dedupe`
  - `test_requeue_front`
  - `test_function_call_mode_events_shape`: the types are `["conversation.item.create", "conversation.item.create", "response.create"]` and the `call_id`s match.
  - `test_cross_team_instruction_names_sender`: the active role is sales_lead and `from_role` is engineer, so the instructions contain `"Dwight"`.
  - `test_user_message_mode_prefix`
- [ ] **Step 2:** Run `pytest tests/gateway/test_injector.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gateway): quiet-gap injection and notification queue`.

### Task A7: CallSession and `WS /call/{role_id}` (Checkpoint 1)

**Files:**
- Create: `backend/gateway/call_session.py`, `backend/tests/gateway/test_call_session.py`
- Modify: `backend/gateway/http.py` (add the websocket route)

**Interfaces:**
- `CallSession(role, client_ws, connect_upstream: Callable[[], Awaitable[Upstream]], ctx: CallContext, queue: NotificationQueue, bus: EventBus, memory: CallMemory, mode: str, clock=time.monotonic)`
- `Upstream` is a protocol: `async send(str)`, `async __aiter__` over raw JSON strings, `async close()`.
- `async run() -> CallRecord`. In order, it:
  1. connects upstream
  2. sends `session.update` (`instructions` from A4, `voice`, `tools_for(role)`, `audio.input.turn_detection`, `input_audio_transcription`)
  3. sends `response.create` with `greeting_instructions`
  4. emits `call.started` to the client and `agent.status {role, state: "on_call"}` to the bus
  5. runs three loops until any of them ends:
     - **client → upstream:** binary → `input_audio_buffer.append` (base64); `{"type":"hangup"}` → end
     - **upstream → client:**
       - `response.output_audio.delta` → binary frame
       - `response.output_audio_transcript.delta/done` → `transcript.assistant.*`
       - `conversation.item.input_audio_transcription.completed` → `transcript.user`
       - `response.created`/`response.done` → `agent.speaking`
       - `speech_started` → `barge_in`
       - a client `function_call` in `response.done` → `run_tool`, then `function_call_output` + `response.create`, and emit `tool.called`
       - `session.idle_timeout`/`session.max_duration_reached`/`error` with a fatal type → end with that reason
     - **injector tick (every 250 ms):** if `queue` isn't empty and `turn.ready()`, send `injection_events(...)` and emit bus `ping {to_role: role.id, ...}`; if `speech_started` arrives before the matching `response.created`, `requeue_front` the result
  6. in `finally`: closes upstream, emits `call.ended {reason}`, `agent.status idle`, and `memory.finish(record)`
- `ctx.on_task_started` emits `task.started` to the client and `task.updated` to the bus.
- The WS route rejects a second concurrent call by closing with `4409`, and sets and clears `app_state.active_call`.

- [ ] **Step 1: Write failing tests** with a `FakeUpstream` (scripted list of server events, records what's sent) and a `FakeClientWS`:
  - `test_first_messages_are_session_update_then_greeting`: `session.update` includes `voice == role.voice` and the transcription model `higgs-stt-3.1`.
  - `test_audio_delta_forwarded_as_binary`
  - `test_client_function_call_runs_tool_and_continues`: the sent events end with `function_call_output` and then `response.create`.
  - `test_server_executor_call_ignored`: for `web_search` with `executor: "server"`, nothing is sent back.
  - `test_speech_started_sends_barge_in`
  - `test_injection_after_quiet_gap`: queue one result, script `response.done`, advance the fake clock 2 s, and assert the injection events were sent plus a bus `ping`.
  - `test_idle_timeout_ends_call_with_reason`
  - `test_client_disconnect_closes_upstream_and_saves_call`
  - `test_second_call_rejected_4409` (route-level, via `TestClient`)
- [ ] **Step 2:** Run `pytest tests/gateway/test_call_session.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it. Use `websockets.connect(BOSON_REALTIME_URL, additional_headers=AUTH_HEADERS, ssl=SSL_CONTEXT, max_size=None)` for the real `connect_upstream`.
- [ ] **Step 4:** Run it again. Expected: PASS. Then **Checkpoint 1:** with C's call window (or `spikes/realtime_spike.py` pointed at `ws://localhost:8000/call/ceo`), talk to Michael and ask "How's the branch doing?". Expect the overview numbers, spoken.
- [ ] **Step 5:** Commit `feat(gateway): call session over Higgs Realtime`.

### Task A8: Call memory

**Files:**
- Create: `backend/gateway/memory.py`, `backend/tests/gateway/test_memory.py`

**Interfaces:**
- `@dataclass CallRecord`: `call_id`, `role`, `started_at: float` (wall clock), `ended_at`, `transcript: list[tuple[str, str]]` (speaker id or `"user"`, text), `touched_task_ids: set[str]`, `summary: str = ""`
- `CallMemory(dir: Path = backend/data/calls, summarize_fn=summarize)`:
  - `start(role) -> CallRecord`
  - `async finish(record, company)`: summarizes, writes `<call_id>.json`, and adds the comment `"Call note: <summary>"` to each touched task via `company.add_comment`, ignoring `CompanyUnavailable`
  - `recent_summaries(n=3) -> list[str]`: formatted `"With {name} ({minutes} min ago): {summary}"`, newest first
- `async summarize(transcript, client: anthropic.AsyncAnthropic | None = None) -> str` uses model `claude-haiku-5-5` with `max_tokens=150` and the prompt "Summarize this call in 2 sentences for a colleague". On any exception, it returns the last 6 lines joined.
- A7 records transcripts and touched task IDs (from `delegate_task` and `get_issue`) into the record.

- [ ] **Step 1: Write failing tests:**
  - `test_summarize_fallback_last_six_lines`: the client raises; the result contains line 7 and not line 1.
  - `test_finish_writes_file_and_comments_touched_tasks`
  - `test_recent_summaries_newest_first_limit_3`
  - `test_finish_tolerates_company_unavailable`
- [ ] **Step 2:** Run `pytest tests/gateway/test_memory.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it, and wire `memory.recent_summaries()` into A4's `build_briefing` call in A7.
- [ ] **Step 4:** Run `pytest -v`, the whole backend. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gateway): cross-call memory`.

### Task A9: Wire the watcher and run the end-to-end loop (Checkpoint 2)

**Files:**
- Modify: `backend/gateway/app_state.py`, `backend/main.py` (startup/shutdown)

**Interfaces:**
- Consumes `TaskWatcher` (B9).
- `on_update(issue)` publishes `task.updated`, and `agent.status working|idle` for `issue.assignee_role`.
- `on_complete(result)`:
  - publishes `task.completed`
  - if `active_call` is set, does `queue.push(result)`; otherwise pushes too, so the next call's briefing gets it from `queue.pending()`, and publishes `ping {to_role: null, ...}`
  - a call drains matching items from `queue` when injected, or when the briefing for that role included them

- [ ] **Step 1: Write a failing test** in `test_http.py`: `test_completion_with_no_call_publishes_null_ping`. Use `MockCompany.complete` and one `watcher.poll_once()`; the bus receives `task.completed` and then `ping` with `to_role is None`.
- [ ] **Step 2:** Run `pytest tests/gateway/test_http.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the startup wiring: start the watcher on startup and stop it on shutdown.
- [ ] **Step 4:** Run `pytest -v`. Expected: PASS. Then, **with `COMPANY_BACKEND=paperclip`**, walk through the §8 storyline end to end with B and C: Ryan delegates → you hang up → call Jim → Dwight's completion is announced mid-call without cutting anyone off.
- [ ] **Step 5:** Commit `feat(gateway): task watcher wiring and live pings`.
