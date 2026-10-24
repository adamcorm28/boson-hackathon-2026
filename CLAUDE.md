# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A hackathon project (Boson AI × MScAC Higgs Audio Hackathon, demo recorded before 3 PM Sat 2026-10-24). You "call" AI employees of a parody **Dunder Mifflin Scranton** in a retro pixel-art office. Each call is a live Higgs Realtime voice session. The employees can delegate slow work to background Paperclip agents running Claude Code, and finished work is announced mid-conversation.

**Read before building:**
- `docs/superpowers/specs/2026-10-23-voice-company-design.md`: the design, which is the binding authority.
- `docs/superpowers/plans/2026-10-23-voice-company-index.md`: the shared contracts between workstreams, plus ports and env vars.
- One plan per workstream in `docs/superpowers/plans/`:
  - A: voice gateway (`backend/gateway/`)
  - B: company layer and Paperclip (`backend/company/`, `paperclip/`)
  - C: arcade frontend (`frontend/`)

Workstreams A (gateway) and B (company layer + Paperclip) are built; check `git log` for what has landed since.

## Commands

The backend uses Python 3.11+ in a venv at `backend/.venv`.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set BOSON_API_KEY (and ANTHROPIC_API_KEY, COMPANY_BACKEND, ...)
.venv/bin/uvicorn main:app --reload --port 8000
.venv/bin/pytest                                   # all tests (pytest.ini: asyncio_mode=auto, pythonpath=.)
.venv/bin/pytest tests/company/test_mock.py::test_create_task_marks_voice_origin -v   # one test
```

`make` lists common commands (`make setup`, `make test`, `make gateway`, `make seed`, `make reset-repo`, `make paperclip-start|stop|status|logs`). Full local setup (venvs, demo repo, a local Paperclip at `:3100`, the seeded company): `make setup` = `scripts/setup_local.sh` (idempotent; see README.md). Each machine runs its own Paperclip; `paperclip_ids.json` is per-machine and optional, because the client finds the seeded company by name. Agent skills and their tests have their own venv: `paperclip/.venv/bin/pytest paperclip/tests`. The frontend will be Vite at `:5173`, with tests run by `npx vitest run`.

## Architecture

- **`backend/main.py`** (FastAPI) wraps the Boson APIs: `/tts`, `/avatar/*`, `/realtime/client-secret`, and a blind relay at `WS /realtime`. Endpoints and models come from env vars (see `.env.example`). The realtime URL constant is `REALTIME_URL`.
- **Voice gateway (`backend/gateway/`):**
  - It owns the Higgs Realtime session server-side. A `CallSession` per call connects the browser socket (`WS /call/{role_id}`, binary PCM16 24 kHz frames) to Boson.
  - It builds instructions from `backend/roles/<role>.yaml` plus a live briefing, and runs tool calls against the company layer.
  - It injects completed-task results only in quiet gaps. It also nudges the model when it claims to delegate or look something up without calling the tool.
  - It also serves `/roles`, `/board`, `/tasks/{id}`, the `/events` SSE stream, and `/artifacts/*`. With the mock company, `POST /dev/complete/{task_id}` fakes a finished task.
  - Per-machine voices (e.g. teammates' clones) go in the gitignored `backend/data/voice_overrides.yaml` (`role_id: voice_<id>`), not in the role files.
  - Rehearse without Paperclip or the frontend: `backend/dev/README.md` (`talk.py` to call an agent with your mic, `scenario.py` for the automated storyline check, `SIMULATE_WORK_SECONDS` for fake work bodies).
- **Company layer (`backend/company/`):**
  - `types.py` is **shared contract 1**. Don't change a signature without coordinating with the gateway owner.
  - `get_company()` picks `MockCompany` (default, in-memory seed from `company/data/issues_seed.json`) or `PaperclipCompany` (`COMPANY_BACKEND=paperclip`).
  - The mock exists so the gateway and frontend never wait on Paperclip. It has the test hooks `set_status()` and `complete()`.
- **One employee, two bodies.**
  - The voice body is a Realtime session: fast, with ≤ 6 tools, all names from `VOICE_TOOL_NAMES`.
  - The work body is a Paperclip `claude_local` agent: slow and deep.
  - The voice body's `delegate_task` creates a Paperclip issue. The work body finishes with a comment `RESULT: <summary>` plus `ARTIFACT: <kind> <url> <label>` lines. A task counts as complete only when its status is `in_review`/`done` **and** a `RESULT:` comment exists.
- **Research:** every employee has a `research(question, topic)` voice tool for outside-world or in-depth questions. It creates a `kind: research` task for themselves that runs on **Claude Opus 5.5** through a per-task adapter override (`engine: cli`, `RESEARCH_MODEL`), because Paperclip's bundled Claude Code can't run 5.5. The result is pinged like any task. The full brief (`artifacts/research-*.md`) comes back through `get_issue` and the briefing's "Research you finished recently" section.
- **Engineer demo repo:** `../dunder-mifflin-infinity/`, a separate git repo with a seeded bulk-discount bug. Reset it with `git reset --hard seeded-bug`.

## Higgs Realtime gotchas (from Boson docs)

- The protocol is OpenAI-Realtime-compatible, but **there is no MCP** and inserted messages can only have role `user` or `assistant` (no `system`).
- With `server_vad`, `response.create` **interrupts** an in-flight response. Never send it while a response is active, except right after a client tool's `function_call_output`.
- `web_search` is a server tool (`{"type": "web_search"}`): skip `function_call` items with `executor: "server"`, and never answer them.
- Sessions close after 5 minutes of user silence (`session.idle_timeout`). User transcripts need `input_audio_transcription: {"model": "higgs-stt-3.1"}`.

## Project rules

- **Likeness:** characters from *The Office* are text personas only. Never clone the actors' voices or use their photos. Voices are Boson presets for now (Michael `marcus`, Dwight `jake`, Jim `oliver`, Ryan `default`); teammates' own cloned voices are a stretch goal. Faces are original pixel art.
- **Personas:** this simulates a well-run company; the Office is only a fun layer. Every character is excellent and cooperative, leads with the answer, never refuses, stalls or lets banter affect the work; at most one comedy bit per reply, and every number comes from tools.
- **Commits and PRs:** no Claude or AI attribution. No `Co-Authored-By: Claude`, no "Generated with Claude Code".
