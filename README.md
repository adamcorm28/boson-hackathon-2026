# Dunder Mifflin Infinity Voice™

**A company you can call.** Every employee is an AI agent with a role, a personality, a voice and a face. You phone them and talk in real time: ask how the quarter is going, interrupt them, tell them to fix something. Slow work goes to a background coding agent while the conversation carries on, and when the work is done they tell you, even if you're on a call with someone else at the time.

Built for the **Boson AI × MScAC Higgs Audio Hackathon** (October 2026). Voice runs on **Boson Higgs Realtime**, faces on **Higgs Avatar**, and the background work on **Paperclip** agents running **Claude Code**. Our company is a parody of Dunder Mifflin Scranton from *The Office*, because everyone already knows who does what there. The engine underneath works for any team.

- **Demo video:** _add the link before submitting_
- **Product brief:** [docs/product-brief.md](docs/product-brief.md)
- **Design spec:** [docs/superpowers/specs/2026-10-23-voice-company-design.md](docs/superpowers/specs/2026-10-23-voice-company-design.md)

## What you can do

- **Call any of five employees,** as an audio call or a video call with a lip-synced live avatar. Pick them from a phone-style contact list (classic mode), or walk up to their desk in a pixel-art office (arcade mode).
- **Talk naturally.** Each call is a live Higgs Realtime session, so you can cut anyone off mid-sentence and they stop and listen.
- **Get real answers.** Each employee is briefed on the live state of the company when you dial (open tasks, flags, what you discussed last time), and pulls every number from a tool: financials, the CRM pipeline, the inbox, the task board.
- **Hand off real work.** "Have Dwight fix the checkout bug" creates a task on the company board. A Claude Code agent picks it up, fixes the bug in a real repo, runs the tests and opens a pull request.
- **Keep talking while it runs.** When the work finishes, the person you're talking to tells you in the next pause, in their own words, without cutting you off.
- **Ask for research.** Every employee can research the outside world (competitors, markets, prospects) on Claude Opus 5.5 and send back a written brief or a PDF.
- **See everything.** A shared task board updates live, toasts announce finished work, a result viewer shows diffs, PRs and decks, and a Documents panel collects every file the team produced.

## Where Higgs Audio is used

| Boson model / API | What it does here |
|---|---|
| **Higgs Realtime** (`higgs-realtime`) | The *voice body* of every employee: low-latency speech-to-speech with server VAD and barge-in, function calling into the company tools, and the server-side `web_search` tool. |
| **Higgs STT** (`higgs-stt-3.1`) | Live transcripts of what you say, shown in the call window and used for call memory. |
| **Voice cloning** (`voice_<id>`) | Each employee speaks with a voice cloned from a teammate's recorded impression of the character, never the actor's voice. Boson presets are the fallback. |
| **Higgs Avatar, live** (LiveKit sessions) | Video calls: the employee's realtime audio drives a lip-synced preset avatar, which goes quiet the instant you interrupt. |
| **Higgs Avatar, video** (`higgs-avatar`) + **Higgs TTS** (`higgs-tts-3`) | Optional faces from a photo you own: idle and talking loops rendered once and cached. |

## Quick start (about 10 minutes, no Paperclip needed)

This runs the whole voice experience on an in-memory company. Delegated tasks "finish" after a timer with a written summary instead of a real code change.

**You need:** Python 3.11+, Node 24, a Boson API key, Chrome, and headphones. An Anthropic API key (`ANTHROPIC_API_KEY`) is optional: it writes the call summaries that employees remember, and without it they remember your last few lines instead.

```bash
git clone https://github.com/adamcorm28/boson-hackathon-2026.git
cd boson-hackathon-2026

# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
#   in backend/.env set:
#     BOSON_API_KEY=<your key>
#     COMPANY_BACKEND=mock
#     SIMULATE_WORK_SECONDS=45
#     VOICE_OVERRIDES=none      # our cloned voices belong to our Boson account; this uses Boson presets
cd ..

# Frontend
cd frontend && npm install && cd ..

# Run both (gateway on :8000, app on :5173)
make up-mock
```

Open **http://localhost:5173** in Chrome, allow the microphone, and **wear headphones** (through speakers the agent hears itself and stops talking).

**Try this:**
1. Call **Michael**: *"How's the branch doing?"*, then *"Anything I should worry about?"*
2. Call **Ryan**: *"What's going on with Infinity?"*, then *"Have Dwight fix it."* Open the board (**B**) and watch the card move.
3. Call **Jim**: *"How's the pipeline looking?"* Interrupt him halfway through. Then just chat. About 45 s after Ryan's hand-off, Jim tells you Dwight is done.
4. Click the toast to open the result.

**Video calls** need a LiveKit Cloud project (free tier is fine): set `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` in `backend/.env`. Without them, choose **Audio** when you dial.

## Full setup (real agents doing real work)

This adds a local Paperclip company whose five agents run Claude Code, so a hand-off really fixes code, builds decks and writes research.

**You need** everything above, plus Node ≥ 24.11, git, the GitHub CLI (`gh auth login`), and **Claude Code installed and logged in**. The agents run on your Claude login, so their work uses your subscription. The engineer works in the demo repo [`thomas-m1/dunder-mifflin-infinity`](https://github.com/thomas-m1/dunder-mifflin-infinity), which has a seeded bug.

```bash
make setup                                  # = scripts/setup_local.sh; safe to re-run
# then in backend/.env: COMPANY_BACKEND=paperclip, and unset SIMULATE_WORK_SECONDS
make up                                     # Paperclip (:3100) + gateway (:8000) + app (:5173)
```

`make setup`:
- creates `backend/.venv` and `paperclip/.venv`
- clones the demo repo next to this one
- starts a local Paperclip at http://127.0.0.1:3100 (log at `~/.paperclip/dev-server.log`)
- seeds Dunder Mifflin: five agents, an org chart and 10 tasks

Each machine runs its own Paperclip and gets its own company and board. `paperclip_ids.json` is optional, because the client finds the seeded company by name.

**Day to day:**

| Command | What it does |
|---|---|
| `make up` / `make up-mock` | Boot everything (Ctrl+C stops it) |
| `make paperclip-status` / `-start` / `-stop` / `-logs` / `-ui` | Manage the local Paperclip |
| `make seed` | Re-seed after editing personas, `AGENTS.md` or seed data |
| `make reset-demo` | Full reset: Paperclip tasks, runs and sessions, the demo repo, GitHub PRs and branches, artifacts and call logs, then re-seed |
| `make reset-repo` | Only put the demo repo back at the seeded bug |
| `make test` | All Python tests |
| `make` | List every command |

## Using the app

| | Classic mode | Arcade mode |
|---|---|---|
| Look | A phone contact list with profiles, light and dark | A pixel-art Scranton office with a whiteboard HUD |
| Call someone | **↑ ↓** select, **Enter** call | **← ↑ ↓ →** walk to their desk, **E** call |
| Either mode | **M** switch mode · **B** task board · **F** Documents · **Esc** hang up / close | **Q** turns idle office chatter on and off |

Dialing asks **Audio** (A) or **Video** (V). During a call, the window shows the live transcript, a waveform, task chips when work is handed off, and any files the employee just finished. Walking more than 2 tiles from a desk in arcade mode hangs up.

## The team

| Employee | Role | Their job | Tools on a call |
|---|---|---|---|
| **Michael Scott** | Regional Manager (CEO) | Q4 targets, KPIs, the inbox; hands work to anyone | company overview, inbox, board, delegate, handbook, research |
| **Kevin Malone** | Accounting (CFO) | P&L, margin, forecasts, what the AI staff costs | financials, AI spend, board, delegate, handbook, research |
| **Ryan Howard** | Engineering Lead | Owns the Infinity ordering site; triages bugs, assigns and reviews | my work, board, delegate, handbook, web search, research |
| **Dwight Schrute** | Engineer | Fixes and builds Infinity, runs tests, opens PRs | my work, board, delegate, handbook, research |
| **Jim Halpert** | Sales Lead | Pipeline and deals, new leads, pitch decks | pipeline, deals, my work, delegate, web search, handbook, research |

The characters are text personas only, written as excellent, cooperative colleagues: the Office humor is limited to one bit per reply and never gets in the way of the work.

## How it works

```
 Browser (React, :5173)                Voice gateway (FastAPI, :8000)                Boson
 ┌───────────────────────┐  PCM16 WS   ┌──────────────────────────────┐   WS    ┌──────────────────┐
 │ contact list / office │────────────▶│ CallSession per call         │────────▶│ Higgs Realtime   │
 │ call window + avatar  │◀────────────│  · persona + live briefing   │◀────────│ (+ STT, web_search)│
 │ board, toasts, docs   │◀── SSE ─────│  · tool router (scoped/role) │         ├──────────────────┤
 └───────────────────────┘             │  · quiet-gap result injector │────────▶│ Higgs Avatar     │
                                       │  · cross-call memory         │         └──────────────────┘
                                       └──────────────┬───────────────┘
                                                      │ company layer (mock or Paperclip)
                                       ┌──────────────▼───────────────┐
                                       │ Paperclip (:3100): org chart, │──▶ Claude Code agents
                                       │ issues, comments, runs       │    (fix code, decks, research
                                       └──────────────────────────────┘     on Opus 5.5, PDFs)
```

**One employee, two bodies.**
- The **voice body** is a Higgs Realtime session. It's fast and has a handful of tools scoped to its role. At dial time the gateway builds its instructions from `backend/roles/<role>.yaml` plus a live briefing: open tasks, flags, recent calls and finished research.
- The **work body** is a Paperclip `claude_local` agent: slow and thorough. `delegate_task` (or `research`) creates a Paperclip issue assigned to it. It finishes with a `RESULT:` comment plus `ARTIFACT:` lines (diff, PR, deck, PDF). A watcher notices, and the result is queued for whoever you're talking to.

**Getting results into a live call.** The gateway tracks whether you're speaking and whether the model is mid-reply. When both are quiet for about 1.5 s, it inserts the result as a tool output and asks the model to tell you in character. It never cuts anyone off, and it never sends `response.create` while a reply is in flight (with server VAD that would interrupt it). It also nudges the model when it *says* it will delegate or check something without calling the tool.

**Repo layout:**

| Path | What's there |
|---|---|
| `backend/main.py` | FastAPI app: Boson API wrappers, mounts the gateway |
| `backend/gateway/` | Call sessions, instructions and briefing, tools, injector, memory, avatars, events (SSE) |
| `backend/company/` | The company layer: `types.py` (shared contract), `mock.py`, `paperclip.py`, the watcher, the data tools |
| `backend/company/data/` | Seed data: financials, CRM, inbox, KPIs, handbook, issues |
| `backend/roles/*.yaml` | One file per employee: persona, voice, tools, responsibilities |
| `backend/dev/` | Rehearse without the frontend: `talk.py`, `scenario.py`, `call_client.py` ([README](backend/dev/README.md)) |
| `paperclip/` | Company seed, agent instructions (`agents/*/AGENTS.md`), skills (`pitch-deck`, `excel-model`, `pdf-report`), the demo reset |
| `frontend/` | React + Vite app: classic and arcade modes, call window, board, result viewer, Documents |
| `scripts/` | `setup_local.sh`, `up.sh` |
| `docs/` | Product brief, demo and presentation scripts, design spec, plans, spike findings |

## Adding an employee

1. Write `backend/roles/<role_id>.yaml`: name, title, voice, persona, `voice_tools` (names from `VOICE_TOOL_NAMES` in `backend/company/types.py`), responsibilities.
2. Add the matching Paperclip agent in `paperclip/agents/<role_id>/AGENTS.md` and the seed, then `make seed`.
3. Optional: a cloned voice in `backend/data/voice_overrides.yaml`, a live avatar in `backend/data/live_avatars.yaml`.

## Development

```bash
make test                                    # backend (gateway + company) and Paperclip-side tests
backend/.venv/bin/pytest tests/company/test_mock.py -v                  # one file (run from backend/)
cd frontend && npx vitest run                # frontend tests
cd frontend && npm run dev:mock              # frontend against a fake gateway, no backend
cd frontend && npm run check:gateway         # contract check against a running gateway (no Boson credits)
make talk ROLE=eng_lead                      # call an agent from the terminal with your mic
make scenario                                # automated demo storyline, prints PASS/FAIL
```

`POST /dev/complete/{task_id}` finishes a mock task by hand. More in [backend/dev/README.md](backend/dev/README.md). Contributors working with Claude Code should read [CLAUDE.md](CLAUDE.md) first.

## Troubleshooting

| Problem | Fix |
|---|---|
| The agent stops mid-sentence by itself | It hears itself through the speakers. Use headphones. |
| "Mic blocked" | Allow the microphone for `localhost:5173` in Chrome, then **Retry mic**. |
| "Already on a call" | Another tab (or `make talk`) holds the call. Close it and redial. |
| A call ends on its own | Boson closes sessions after 5 minutes of silence. Redial. |
| Silence or an error when a call starts | Check `BOSON_API_KEY`. If you're not on our Boson account, set `VOICE_OVERRIDES=none`. |
| Video option greyed out or no picture | Set the three `LIVEKIT_*` variables, or use audio. |
| `make up` says a port is in use | Stop whatever holds :8000 or :5173 (the message names the process). |
| Delegated work never finishes (Paperclip) | `make paperclip-status`, `make paperclip-logs`; check Claude Code is logged in. |

## Known limitations

- One call at a time, one user, no auth; everything runs locally.
- The company data (financials, CRM, inbox) is seeded, not connected to real systems. The voice, tool calls, delegation and agent work are real.
- Real background work needs Paperclip, Claude Code and access to the demo repo; without them, the mock company simulates it.
- Cloned voices are tied to the Boson account that made them.
- Background tasks take minutes, not seconds: a bug fix takes about 2 to 3 minutes, and a deck or research brief takes longer.

## Team

| Who | GitHub | Built |
|---|---|---|
| Thomas Michalski | [@thomas-m1](https://github.com/thomas-m1) | Design and plan, company layer and Paperclip integration, personas and seed data, agent skills, research on Opus 5.5, PDF documents, local setup and tooling |
| Adam Cormier | [@adamcorm28](https://github.com/adamcorm28) | Voice gateway on Higgs Realtime: call sessions, tools, briefing, quiet-gap injection, call memory, delegation guard; Boson endpoints; avatars and live video calls; cloned voices |
| Paul Ellement | _add handle_ | Frontend: arcade office, call window, mic and audio, board, result viewer, HUD and toasts, classic mode with contact profiles and themes, demo script |

## Credits and likeness

*The Office* and Dunder Mifflin belong to their owners; this is a non-commercial parody for a hackathon. The characters are text personas only. We never clone the actors' voices or use their photos: the voices are teammates' own recorded impressions or Boson presets, and the faces are original pixel art or Boson's preset avatars.
