# Hackathon submission answers

Answers for the form at https://www.boson.ai/hackathon#submit. Fill the gaps in _italics_ before sending.

## 1. Project information

**Project name:** Dunder Mifflin Infinity Voice

**Track:** Agents That Act (primary). It also spans Conversation as the Interface and Put a Face to the Voice.

**One-sentence description:**
Call the AI employees of a parody Dunder Mifflin: they talk with you in real time, hand slow work to background coding agents, and tell you mid-call when it's done.

**Write-up (≤ 200 words):**

AI assistants make you type prompts at one chatbot, but that isn't how work gets done. At a real company you call people: you ask how things are going, you ask them to dig into something, and they get back to you.

Dunder Mifflin Infinity Voice is a company you can call. Each employee of a parody Dunder Mifflin (CEO, CFO, engineering lead, engineer, sales lead) is an AI agent with its own role, personality, voice, face and scoped tools. Dial one from a contact list or walk to their desk in a pixel-art office, then talk naturally: interrupt them, ask for numbers, assign work. Slow work like fixing a bug, researching leads or building a deck goes to a background agent while you keep talking. When it finishes, whoever you're on a call with tells you in the next pause, and one click shows the diff, PR or document.

It's for founders, managers and anyone supervising AI agents who wants to check in hands-free, from the car or between meetings. The Office is just the skin: swap in your real team and systems, and the same engine runs your company.

## 2. Demo video

- **Link:** _public YouTube or Drive link, viewable without requesting access_
- **Try-it URL:** none (it runs locally; see the README quick start).

## 3. Repository

- **URL:** https://github.com/adamcorm28/boson-hackathon-2026
- **Pinned commit:** _tag the final commit (`git tag submission && git push origin submission`) and paste the SHA_
- **Setup instructions:** README → *Quick start* (mock company, needs only a Boson API key) and *Full setup* (Paperclip + Claude Code).

## 4. How you built it (≤ 200 words)

**Higgs Realtime** is every employee's voice body. A FastAPI gateway owns one session per call, relays the browser's PCM16 audio, uses server VAD for barge-in, and builds instructions from a role file plus a live company briefing. Each role gets scoped function tools (financials, CRM, inbox, task board, `delegate_task`, `research`), plus Boson's server-side `web_search`. **Higgs STT 3.1** transcribes the user for the call window and cross-call memory. **Higgs Avatar** gives video calls a lip-synced live face, driven by the same realtime audio and muted on barge-in. **Voice cloning** gives each employee a voice recorded by a teammate.

The work body is a Paperclip agent running Claude Code. `delegate_task` creates an issue, and the agent fixes a real repo and opens a PR, builds a deck, or researches on Claude Opus 5.5 into a PDF.

The hard part was announcing results mid-conversation. Under server VAD, `response.create` interrupts an in-flight reply, so the gateway tracks speech and response state and injects a synthetic tool result only after about 1.5 s of quiet, and the employee says it in character. A guard also nudges the model when it claims to delegate without calling the tool.

## 5. Team information

| Name | GitHub | Work |
|---|---|---|
| Thomas Michalski | _@thomas-m1 (confirm)_ | Design and plan; company layer and Paperclip integration; personas and seed data; agent skills (decks, Excel models, PDF reports); research on Opus 5.5; documents; local setup and tooling |
| Adam Cormier | @adamcorm28 | Voice gateway on Higgs Realtime (call sessions, tools, live briefing, quiet-gap injection, call memory, delegation guard); Boson API endpoints; avatars and live video calls; cloned voices |
| Paul Ellement | _@handle_ | Frontend: arcade office, call window, mic capture and playback, task board, result viewer, HUD and toasts; classic mode with contact profiles and light/dark themes |

**Notes and known limitations:**
- Runs locally: one call at a time, one user, no auth.
- Company data (financials, CRM, inbox) is seeded. Voice, tool calls, delegation and the agents' work are real.
- Real background work needs a local Paperclip, Claude Code, and access to our demo repo. Without them, the mock company simulates finished work (`COMPANY_BACKEND=mock`, `SIMULATE_WORK_SECONDS=45`).
- Our cloned voices belong to our Boson account. On another key, set `VOICE_OVERRIDES=none` to use Boson presets.
- Video calls need a LiveKit Cloud project; audio calls don't.
- *The Office* characters are text personas only: no actor voices or photos.
