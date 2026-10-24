# Voice Company: design

**Status:** draft for team approval · **Date:** 2026-10-23 · **Deadline:** recorded demo ready before 3:00 PM, Sat 2026-10-24

## 1. Intent

A simulated company whose employees are AI agents you can **call**. You pick someone from the company directory and get a Zoom-style call screen. You talk to that employee in real time through Higgs Realtime, exactly as you would with a real employee: ask what they're working on, get progress updates, ask questions, tell them to do something.

The employees are real agents underneath. Each one is a Paperclip agent with its own role, manager, task board and tools. When you ask for something that takes real work (fix a bug, research leads, build a deck), the voice agent hands it off and keeps talking with you. When the work finishes, you get pinged, even if you're on a call with someone else at that moment.

**Why it wins:** it puts Boson's two judged themes, real-time voice and tool calling, at the centre. It also solves a real limitation of voice models: they can't do long reasoning. A fast voice front end delegates slow work to background agents.

## 2. Goals, non-goals, anti-goals

**Goals**
- Call any one of five employees: CEO, CFO, Eng Lead, Engineer, Sales Lead. One call at a time.
- Every employee knows the live state of the company (tasks, flags, recent calls) when the call starts.
- Voice agents can delegate long-running work and keep talking. Results are announced when they're ready, including **cross-team pings** ("Jake from engineering just pinged, the fix is done").
- One shared task board for the whole company, visible in the UI and updating live.
- Roles are modular: adding a role means adding one config file plus one Paperclip agent.
- A 5-minute recorded demo (see §8).

**Non-goals (for now)**
- Group calls or calls between agents, real phone numbers, avatars (stretch goal), multi-user support, auth, deployment.
- A separate company database. Paperclip plus seed files cover it.
- Real third-party SaaS where a mock tells the same story.

**Anti-goals: failure even if it technically works**
- The voice sounds robotic or slow, or dead air follows a tool call.
- Background work stays invisible, so the audience can't tell anything happened.
- The demo depends on a live run that can't finish in a reasonable time on camera.
- An announcement cuts the user or the agent off mid-sentence.

## 3. Constraints and known facts

- **Higgs Realtime:** `wss://api.boson.ai/v1/realtime?model=higgs-realtime`, OpenAI-GA-compatible protocol, PCM16 24 kHz mono, base64 in JSON. Tools are `function` (client-executed) plus a server-side `web_search`. **No MCP.** Messages can only be inserted with roles `user` and `assistant` (no `system`). `response.create` accepts per-response `instructions`. With `server_vad`, `response.create` interrupts an in-flight response. Sessions close after 5 minutes of user silence (`session.idle_timeout`). The concurrency limit isn't published. Turn on user transcription with model `higgs-stt-3.1`.
- **Voices:** TTS presets are `chloe, eleanor, jake, marcus, nora, oliver`. It's **unverified** whether they work in Realtime; fall back to cloned `voice_<id>` or `default`.
- **Paperclip:** self-hosted Node 24 + embedded Postgres at `http://localhost:3100/api`. In `local_trusted` mode the API needs no token. Issues have statuses `backlog/todo/in_progress/in_review/blocked/done/cancelled`. Assigning an issue to an agent wakes it. Agents use the `claude_local` (Claude Code) adapter. The full route list is at `GET /api/openapi.json`.
- **Existing code:** `backend/main.py` (FastAPI) already relays the Realtime WebSocket, mints client secrets, and wraps TTS and Avatar. It is a blind relay today.
- **Machine:** Paperclip and Claude Code run on one teammate's laptop, which needs a working Claude Code login. The demo is recorded, so everything can be local.

## 4. Architecture

```
Browser (React)                      Voice Gateway (FastAPI, extends backend/)            Paperclip (:3100)
┌───────────────────┐  WS /call/{role} ┌──────────────────────────────────┐  REST  ┌──────────────────────┐
│ Directory / call  │ ◄──audio+events─►│ CallSession (1 active)           │ ─────► │ Company, agents,     │
│ Transcript        │                  │  • builds instructions at start  │        │ issues (= the board) │
│ Board (live)      │ ◄──SSE /events── │  • routes tool calls             │ ◄───── │ Claude Code runs     │
│ Toasts / results  │                  │  • injects task results          │        └──────────────────────┘
└───────────────────┘                  │ TaskWatcher (polls every 3 s)    │
                                       │ EventBus → SSE + active call     │──WS──► Higgs Realtime
                                       │ Seed data (company/*.json, md)   │
                                       └──────────────────────────────────┘
```

**One employee, two bodies.** Each employee has a **voice body**: a Higgs Realtime session that is fast and shallow and has 3–6 small tools. It also has a **work body**: a Paperclip agent on Claude Code that is slow and deep and has its connectors. Both are built from the same persona file. The voice body's key tool is `delegate_task`, which creates a Paperclip issue.

**The gateway owns the Realtime session.** The browser sends mic audio and receives assistant audio plus UI events over our own WebSocket. The API key, `session.update`, tool execution and result injection all live server side. The existing relay is replaced by (or wraps) a `CallSession` that parses every upstream event.

## 5. Key mechanisms

### 5.1 Call start
1. The browser opens `WS /call/{role_id}`.
2. The gateway loads `roles/{role_id}.yaml` and builds `instructions`:
   - the persona
   - speaking-style rules (short spoken sentences, never read out IDs or URLs)
   - **live briefing**: the role's open issues and statuses, items flagged to the user, a summary of the user's last 3 calls with anyone, and results not yet discussed
   - tool-use rules
3. The gateway sends `session.update` with `voice`, `tools`, `server_vad` (defaults) and `input_audio_transcription: {model: "higgs-stt-3.1"}`.
4. The gateway sends `response.create`, so the employee answers the call first ("Hey, it's Oliver, what's up?").

### 5.2 Fast tools (synchronous, < 1 s)
Read Paperclip or seed data and return JSON straight away through `function_call_output` + `response.create`.

### 5.3 Delegated tasks (asynchronous)
1. The model calls `delegate_task({assignee, title, brief})`.
2. The gateway creates a Paperclip issue assigned to that agent, tagged `origin: voice` with `requested_by_role`. It **immediately** returns `{task_id, status:"started", eta_hint}`, and the model says something like "on it, I'll ping you."
3. `TaskWatcher` polls the voice-originated issues every 3 s. Each work-body agent's instructions require it to finish with a comment starting `RESULT:` (2–4 sentence summary plus artifact links) and to move the issue to `in_review` or `done`. Both signals together mean the task is complete.
4. On completion, an event goes on the `EventBus`. It is shown as a UI toast and also queued for the active call, whoever that call is with.

### 5.4 Result injection (the riskiest piece: spike first)
The gateway tracks `response_active` (from `response.created` to `response.done`) and `user_speaking` (from `speech_started` to `speech_stopped`). When both are false and at least 1.5 s have passed since the last turn ended, it pops the queue and:
1. Sends `conversation.item.create` with a synthetic `function_call` (`name: "task_update"`, new `call_id`).
2. Sends a `function_call_output` with `{task_id, from_role, title, result_summary}`.
3. Sends `response.create` with per-response `instructions`:
   - **Own task:** "Briefly tell the user this is ready and ask if they want to go through it now."
   - **Another employee's task:** "Mention naturally that {name} from {team} just pinged that {title} is done; offer to keep going or suggest they call {name}."
4. If no call is active, the item stays queued. It is delivered in the next call's briefing, and the UI toast remains.

**Fallback if Boson rejects synthetic function_call items:** insert a `user` message with `input_text` `"[notification from system, not the user] …"`, then use the same `response.create`.

### 5.5 Cross-call memory
On hang-up, the gateway saves the call transcript (user transcripts plus `response.output_audio_transcript.done`) to `data/calls/`. It writes a 2-sentence summary, made with the Claude API (`claude-haiku-5-5`), falling back to the last 6 lines if that fails. It also adds a comment on any issue touched during the call. The next call's briefing includes those summaries, which is how the Sales Lead can know you just spoke to the Eng Lead.

### 5.6 "What are you doing right now?"
`get_my_work` includes in-progress issues, the latest agent comment and run status. So calling the Engineer in the middle of a task gets a real answer.

## 6. Roles

The fictional company is **Kestrel Labs**, about 2 years old. It sells **Kestrel Book**, appointment booking for small clinics.
- Business: ARR $1.2M, 85 customers, burn $95k/mo, runway 14 months.
- Live situation, seeded:
  - The checkout charges the full monthly price ×12 on annual plans, so the annual discount is missing.
  - That bug is stalling the **Acme Dental** deal ($48k ARR).
  - The Q4 goal is to reach 100 customers.

### 6.1 Role config (one file per role, `roles/*.yaml`)
```yaml
id: eng_lead
name: Oliver Park
title: Engineering Lead
reports_to: ceo
paperclip_agent: eng-lead        # shortname in Paperclip
voice: oliver                    # fallback: default
greeting: "Hey, it's Oliver."
persona: |                       # who they are, how they talk, what they care about
  ...
turn_detection: {type: server_vad}   # per-role overrides allowed
voice_tools: [get_my_work, get_board, get_issue, delegate_task, lookup_company, web_search]
can_delegate_to: [engineer, eng_lead]
```

### 6.2 Roster

| Role | Persona (voice) | Voice tools (fast) | Work body does (slow) |
|---|---|---|---|
| **CEO** Eleanor Hart | Calm, big-picture, prioritizes ruthlessly (`eleanor`) | `get_company_overview` (KPIs, flags across teams), `read_inbox` / `read_email`, `get_board`, `delegate_task` (anyone) | Draft email replies, write an investor update |
| **CFO** Nora Lindqvist | Precise, dry humor, numbers first (`nora`) | `get_financials` (P&L, burn, runway), `get_ai_spend` (Paperclip costs API: the real cost of today's AI staff), `delegate_task` | Build an Excel model (openpyxl `.xlsx`), e.g. revenue impact of Acme Dental |
| **Eng Lead** Oliver Park | Thoughtful, explains tradeoffs, protective of the team (`oliver`) | `get_board`, `get_issue`, `get_my_work`, `delegate_task` (→ Engineer) | Triage, write specs, review the Engineer's fix |
| **Engineer** Jake Morales | Energetic, hands-on, a bit nerdy (`jake`) | `get_my_work` (live run status), `get_issue` | **Claude Code on the `kestrel-book` demo repo:** fix, run tests, commit on a branch, open a PR if `gh` is authenticated, otherwise show the local diff |
| **Sales Lead** Marcus Bell | Confident, upbeat, deal-focused (`marcus`) | `get_pipeline` (seeded CRM), `get_deal`, `web_search` (server), `delegate_task` | Research leads, build a pitch deck (python-pptx `.pptx`) |

Every role also gets `lookup_company(topic)`, which searches the handbook. `chloe` stays free for a future role, such as Marketing.

### 6.3 Seeded company data (`company/`)
- `handbook.md`: mission, product, pricing, org, Q4 goals.
- `financials.json`: 12 months of P&L.
- `crm.json`: ~15 deals, including Acme Dental blocked by the pricing bug.
- `inbox.json`: ~6 CEO emails, including an Acme escalation and an investor asking for an update.
- `kpis.json`.
- **Paperclip seed**, via a script calling the REST API:
  - the company and its goal
  - the 5 agents with `AGENTS.md` instructions and the reporting lines CEO → {CFO, Eng Lead, Sales Lead}, Eng Lead → Engineer
  - about 10 issues across teams, including the bug, flagged by the Eng Lead
- **`kestrel-book` demo repo:** a small web app with a pricing and checkout module, a failing unit test that reproduces the bug, and a fix of about 5 lines.

Mocks stay behind tool functions, so a real connector (AgentMail, HubSpot, Stripe) can replace one later without changing the voice layer.

## 7. UI: retro arcade office (direction leaning, not final)

The office is a top-down pixel-art floor with one cubicle per employee. You walk your character over to a cubicle and press a key to start a call. The call opens as a retro-styled video-call window over the office.

- **Office map:** cubicles are generated from `GET /roles`, so a new role gets a desk automatically. Each role's YAML can carry an optional `desk` position and `sprite`; otherwise desks are auto-placed.
- **Cubicle state is visible at a glance**, driven by SSE:
  - monitor glowing or typing animation: the agent has an `in_progress` task
  - "!" bubble over the employee: they have a finished result for you
  - phone-ringing icon: someone pinged while you're on another call
- **Call window:** pixel portrait with a talking animation and waveform, live transcript, chips for "tasks started this call", and hang-up (Esc). Walking away also hangs up.
- **Kanban board:** a whiteboard on the office wall. Walk up to it, or press B, to open the full board. A minimap version can stay on the HUD so the audience sees cards move during calls.
- **Pings and results:** a toast in arcade style ("JAKE: fix is done!"). Opening it shows the result viewer, framed as a monitor or printout: the RESULT summary plus the PR/diff, `.pptx` or `.xlsx`.
- **Audio:** an AudioWorklet captures at 24 kHz PCM16 and plays assistant audio back. Local playback stops on the `barge_in` event.
- **Engine:** up to the frontend owner. Cheap options are Phaser 3 or KAPLAY inside React, or plain React with a CSS tile grid. Walking only needs arrow keys and collision with walls.

## 7a. Interface contracts between workstreams

These let all three streams start at once against mocks.

**Frontend ↔ Voice gateway** (owned by A, mocked by C until it's ready)
- `GET /roles`: `[{id, name, title, reports_to, voice, sprite?, desk?}]`
- `GET /board`: `{columns: {backlog: [...], todo: [...], in_progress: [...], in_review: [...], blocked: [...], done: [...]}}`. Each card is `{task_id, title, assignee_role, status, origin}`.
- `GET /tasks/{task_id}`: `{task_id, title, assignee_role, status, result_summary, artifacts: [{kind: "pr"|"diff"|"pptx"|"xlsx"|"link", url, label}]}`
- `GET /events` (SSE):
  - `agent.status {role, state: "idle"|"working"|"on_call"}`
  - `task.updated {task_id, status, assignee_role, title}`
  - `task.completed {task_id, from_role, title, summary}`
  - `ping {to_role|null, from_role, task_id, text}`
- `WS /call/{role_id}`:
  - Client → server: binary frames of PCM16 24 kHz mono mic audio, or the JSON `{type: "hangup"}`.
  - Server → client: binary frames of PCM16 24 kHz assistant audio, plus these JSON events:
    - `call.started {role}`
    - `transcript.user {text}`
    - `transcript.assistant.delta {text}`
    - `transcript.assistant.done {text}`
    - `agent.speaking {value: bool}`
    - `barge_in`
    - `tool.called {name, args}`
    - `task.started {task_id, title, assignee_role}`
    - `call.ended {reason}`

**Voice gateway ↔ Company layer** (owned by B as the Python package `backend/company/`, consumed by A)
- `paperclip_client.py`:
  - `list_issues(role=None, status=None)`
  - `get_issue(task_id)`, which includes comments
  - `create_task(assignee_role, title, brief, requested_by_role) -> task_id`
  - `get_agent_status(role)`
  - `get_costs()`
- `data_tools.py`: pure functions returning dicts, such as `company_overview()`, `get_pipeline()`, `get_deal(name)`, `get_financials()`, `read_inbox()`, `read_email(id)` and `lookup_company(topic)`.
- **A mock implementation (in-memory, backed by the seed JSON) ships first**, so A never waits on Paperclip. B then swaps in the real client behind the same functions.
- A owns the tool **schemas** and the router. B owns what the tools **return**.

## 8. Demo storyline (5 min, recorded, editable)
1. **CEO:** "Give me the state of the company." Gets KPIs, Q4 progress, and "Oliver flagged a checkout bug that's blocking Acme Dental, and you have an investor email waiting."
2. **Eng Lead:** "What happened with the bug?" Gets an explanation, then "What do you recommend?", then "Do it." It delegates to the Engineer, and the board card moves to *in progress*.
3. **(Optional cut) Engineer:** "What are you doing right now?" Gets live status from the run.
4. **Sales Lead:** pipeline update and strategy talk. It knows about the bug from call memory: "Once that checkout fix lands I can re-send Acme the quote." Then "Research 5 more clinic chains and build me a deck," which is delegated. → **ping arrives mid-call:** "Jake just pinged, the checkout fix is done."
5. Open the result viewer and show the PR or diff with tests passing. Optionally, a quick CFO call: "What's Acme worth to our runway?" and "What did today's AI work cost?"
6. Close on the deck result and the board, with everything done.

## 9. Build order and workstreams

**Spikes first (tonight, before anything else):**
- **S1:** Realtime voice works with a preset voice. Check whether `jake`, `oliver` and the others are accepted.
- **S2:** the §5.4 injection flow. Delegate, wait 20 s, then inject; check that it is spoken naturally and nothing gets cut off. Test the fallback if needed.
- **S3:** Paperclip is running, a `claude_local` agent is assigned an issue over REST, and it posts a `RESULT:` comment.

**Workstreams (three people). Each owns one spike:**
- **A. Voice (S1, S2):**
  - `CallSession`, which replaces the blind relay
  - tool schemas and router
  - instruction builder: persona plus live briefing
  - result injection and the cross-team ping queue
  - EventBus, SSE, call memory
  - the endpoints in §7a
- **B. Paperclip and architecture (S3):**
  - Paperclip install and the seed script
  - each role's `AGENTS.md` (work-body instructions, including the `RESULT:` convention)
  - role YAMLs (personas, voices) and the `company/` seed data
  - `backend/company/` (mock first, then real)
  - the `kestrel-book` repo with its bug and failing test
  - the pptx/xlsx skills
  - TaskWatcher polling
- **C. Frontend:**
  - arcade office, movement and cubicles
  - call window and audio worklet
  - wall board, toasts and pings, result viewer
  - builds against a mock gateway (a fake WS that plays a WAV, plus fake SSE) until A is ready
  - then the demo script and recording

**Integration checkpoints:**
- ~1:00 AM: a real voice call works in the arcade, with a mock company.
- ~8:00 AM: Paperclip is wired in end to end and the delegate → ping loop works.
- ~11:00 AM: feature freeze, then rehearse the storyline.

**Freeze features about 11:00 AM Saturday, and record by about 1:30 PM.**

## 10. Risks

| Risk | Mitigation |
|---|---|
| Synthetic function_call injection rejected or awkward | Spike S2 first; fallback to a `user` notification message |
| Claude Code too slow on camera | Small seeded bug with a failing test; video cuts; pre-warm the agent |
| Preset voices unavailable in Realtime | Clone voices from TTS preset samples, or use `default` with persona styling |
| Concurrency limit or 5-minute idle close | Only one call at a time; reconnect on close |
| Paperclip setup friction | Spike S3 tonight; seed by script so it can be recreated |
| Tool selection gets worse with many tools | ≤ 6 voice tools per role; heavy work goes to the work body |

## 11. Calls I made (please check)
- The fictional company, its names and numbers, and the checkout bug as the narrative thread.
- Names and voice mapping for each persona.
- The gateway owns the Realtime session instead of the browser talking to Boson directly.
- Completion is detected by polling Paperclip every 3 s, not with webhooks.
- Most external SaaS is mocked behind tool functions. The only real ones are Claude Code, git/GitHub and `web_search`.
- The CEO inbox is seeded JSON; AgentMail is a stretch swap.
- Call summaries use the Claude API (Haiku).
- The frontend is React + Vite + TS.

## 12. Layout (my call)
- `backend/`: the voice gateway (extends `main.py`), plus `roles/*.yaml` and `company/` seed data.
- `frontend/`: the React app.
- `paperclip/seed.py` and `paperclip/agents/<role>/AGENTS.md`.
- `../kestrel-book/`: a **separate git repo**, because the Engineer agent commits there. It is the `cwd` of the Engineer's Claude Code agent.
- `artifacts/`: a shared output folder. Work-body agents write `.pptx`/`.xlsx` files here, and the gateway serves it at `/artifacts/*`. Its absolute path goes into each `AGENTS.md`.
- All work-body agents (CFO and Sales included) use the `claude_local` adapter.

## 13. Left to the builder
- The exact Paperclip endpoints for creating companies and goals, taken from `/api/openapi.json`.
- Audio worklet details, styling and layout.
- Wording of the prompts, as long as they follow §5.1.
