# Arcade Frontend Implementation Plan (Workstream C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A retro pixel-art Dunder Mifflin Scranton office. You walk to an employee's desk to call them over voice, the conference-room whiteboard shows the live company Kanban, and finished work shows up as pings and a result viewer.

**Architecture:**
- A React + Vite + TS single-page app.
- All game and app logic is **pure, tested TypeScript**: the tile map, movement and collision, desk layout, and the reducers for office state, call state and board. Rendering is a thin layer over it. The default is React with a CSS tile grid; the owner may swap in Phaser or KAPLAY, and the pure modules stay.
- A mock gateway with the same interface as the real one lets everything be built before A is ready.

**Tech Stack:** React 18, Vite, TypeScript, Vitest, Web Audio (AudioWorklet), EventSource, WebSocket.

**Spec:** `docs/superpowers/specs/2026-10-23-voice-company-design.md` (§7, §7a, §8). **Index / shared contracts:** `docs/superpowers/plans/2026-10-23-voice-company-index.md`

## Global Constraints

- Gateway at `import.meta.env.VITE_GATEWAY_URL` (default `http://localhost:8000`). `VITE_MOCK=1` switches to the mock gateway.
- Audio is PCM16 little-endian, 24 kHz, mono, in **binary** WS frames both ways. Stop local playback immediately on `barge_in`.
- Desks are generated from `GET /roles`: a known `desk` name maps to a fixed spot, and unknown or missing ones are auto-placed. A new role gets a desk with no code change.
- Layout: reception at the entrance, Michael's office with a door, Jim's and Dwight's desks facing each other, the accounting corner (Kevin), the annex (Ryan), and the conference room whiteboard (the Kanban board).
- Likeness: original pixel-art caricatures only, never photos of the actors.
- Indicators:
  - glowing monitor = `working`
  - "!" over `from_role` after `task.completed`, cleared when that result is opened or that role is called
  - ringing phone = a `ping` with `to_role: null`
  - Toast text: `"<FIRST NAME IN CAPS>: <title> is done!"`
- Controls:
  - arrow keys/WASD move
  - `E` (near a desk) calls
  - `Esc`, or walking more than 2 tiles away, hangs up
  - `B`, or `E` at the whiteboard, opens the board
- A WS close with code `4409` shows "Already on a call".

## Review Focus

- **The mic is denied or there's no input device:** the call window shows "Mic blocked — allow microphone and retry" instead of failing silently. Test it in C3.
- **The SSE connection drops (gateway restart):** auto-reconnect with backoff, then refetch `/board` and `/roles` so the state isn't stale. Test it in C2.
- **Audio arrives faster than real time:** chunks are scheduled back to back with no gaps or overlap, and `stop()` clears everything queued. Test it in C3.
- **Events for unknown roles or tasks** (a new role mid-demo, a stale task): reducers ignore or add them; they never throw. Test it in C5 and C6.
- **A call ends from the server side** (`call.ended` with an idle timeout): the window closes and the employee shows idle without the user pressing anything. Test it in C4.

## File Structure

```
frontend/
  package.json  vite.config.ts  tsconfig.json  index.html  .env.example
  public/worklets/mic-processor.js
  public/sprites/  (michael, dwight, jim, kevin, ryan, player, tiles; 16x16 or 32x32 pixel art)
  src/
    main.tsx  App.tsx  styles.css
    api/types.ts  api/gateway.ts  api/mock.ts  api/index.ts
    audio/pcm.ts  audio/mic.ts  audio/player.ts
    call/callReducer.ts  call/useCall.ts  call/CallWindow.tsx
    office/map.ts  office/movement.ts  office/officeReducer.ts  office/Office.tsx  office/Hud.tsx
    board/boardReducer.ts  board/Whiteboard.tsx
    results/Toasts.tsx  results/ResultViewer.tsx
  src/**/*.test.ts
```

---

### Task C1: Scaffold, types and the gateway client

**Files:**
- Create: the Vite React-TS scaffold in `frontend/`, `src/api/{types,gateway,index}.ts`, `src/api/gateway.test.ts`, `.env.example`

**Interfaces:**
- `types.ts` mirrors §7a exactly:
  - `Role`, `Card`, `Board`, `TaskDetail`, `Artifact`
  - `ServerEvent`: a discriminated union on `type` covering the SSE events `agent.status`, `task.updated`, `task.completed`, `ping`, plus the client-only `{type: "resync"}`
  - `CallEvent`: a union covering `call.started`, `transcript.user`, `transcript.assistant.delta`, `transcript.assistant.done`, `agent.speaking`, `barge_in`, `tool.called`, `task.started`, `call.ended`
- `interface Gateway` has:
  - `fetchRoles(): Promise<Role[]>`
  - `fetchBoard(): Promise<Board>`
  - `fetchTask(id: string): Promise<TaskDetail>`
  - `subscribe(onEvent: (e: ServerEvent) => void): () => void`
  - `openCall(roleId: string): CallSocket`
- `interface CallSocket` has `sendAudio(pcm: ArrayBuffer)`, `hangup()`, `onAudio(cb)`, `onEvent(cb)`, `onClose(cb: (code: number) => void)`.
- `api/index.ts` exports `gateway: Gateway`, the mock or the real one depending on `VITE_MOCK`.
- In `subscribe`, the real client listens to the named SSE events. On error, it reconnects with backoff of 1, 2, 4… seconds, capped at 10, and calls `onEvent({type: "resync"})` after reconnecting.

- [ ] **Step 1: Write failing tests:**
  - `parses SSE ping event into ServerEvent`: use the helper `parseSse(type, data)` exported from `gateway.ts`.
  - `resync emitted after reconnect`: a fake `EventSource` errors once, then opens.
- [ ] **Step 2:** Run `cd frontend && npx vitest run src/api`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(frontend): scaffold and gateway client`.

### Task C2: Mock gateway

**Files:**
- Create: `src/api/mock.ts`, `src/api/mock.test.ts`, `public/mock/greeting.pcm` (any 24 kHz PCM16 clip, e.g. made with `/tts` and `response_format: "pcm"`)

**Interfaces:**
- `createMockGateway(opts?: {speed?: number}): Gateway`:
  - five Dunder Mifflin roles with the spec §6.2 names and desks
  - a board seeded with the bulk-discount card in `todo`
  - `openCall` emits `call.started`, streams `greeting.pcm` as audio with `agent.speaking` true/false, and sends a scripted `transcript.assistant.done`
  - when the user has sent about 2 s of audio, it emits `task.started` and moves the card to `in_progress` over SSE
  - 10 s later it emits `task.completed` from `engineer` and a `ping`
- `speed` scales all timers, so tests use `speed: 1000`.

- [ ] **Step 1: Write a failing test:** `mock scripted sequence`. With fake timers and `speed`, the events seen are `call.started` … `task.started`, then the SSE events `task.updated(in_progress)`, `task.completed` and `ping`, in that order.
- [ ] **Step 2:** Run `npx vitest run src/api/mock.test.ts`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(frontend): mock gateway`.

### Task C3: Audio in and out

**Files:**
- Create: `src/audio/{pcm,mic,player}.ts`, `public/worklets/mic-processor.js`, `src/audio/pcm.test.ts`, `src/audio/player.test.ts`

**Interfaces:**
- `pcm.ts`:
  - `downsample(input: Float32Array, inRate: number, outRate: number): Float32Array` (linear interpolation)
  - `floatTo16(input: Float32Array): ArrayBuffer` (clamped to [-1, 1])
  - `int16ToFloat(buf: ArrayBuffer): Float32Array`
- `mic.ts`: `startMic(onFrame: (pcm: ArrayBuffer) => void): Promise<{stop(): void}>`. The worklet posts Float32 blocks; frames go out about every 40 ms. It throws `MicBlockedError` on `NotAllowedError` or `NotFoundError`.
- `player.ts`: `createPlayer(ctx: AudioContext)` returns `{enqueue(pcm: ArrayBuffer): void, stop(): void, readonly playing: boolean}`. It schedules each chunk at `max(ctx.currentTime, endOfLastChunk)`. `stop()` stops all scheduled sources and resets the schedule.

- [ ] **Step 1: Write failing tests:**
  - `downsample 48k→24k halves length`
  - `floatTo16 clamps`: `[1.5, -2]` → `[32767, -32768]`
  - `round trip within 1/32768`
  - `player schedules back-to-back`: with a fake `AudioContext`, two 100 ms chunks start at 0 and 0.1.
  - `stop clears queued sources`
  - `startMic maps NotAllowedError to MicBlockedError`: mock `getUserMedia`.
- [ ] **Step 2:** Run `npx vitest run src/audio`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(frontend): PCM16 mic capture and playback`.

### Task C4: Call state and call window (Checkpoint 1)

**Files:**
- Create: `src/call/{callReducer,useCall}.ts`, `src/call/CallWindow.tsx`, `src/call/callReducer.test.ts`

**Interfaces:**
- `CallState`:
  - `{status: "idle" | "connecting" | "live" | "ended", roleId: string | null, speaking: boolean}`
  - `lines: {speaker: "user" | "agent", text: string, final: boolean}[]`
  - `tasks: {task_id, title, assignee_role}[]`
  - `error: string | null`
- `callReducer(state, action)`, where actions are `CallEvent`s plus the local actions `{type: "dial", roleId}`, `{type: "closed", code}` and `{type: "mic_blocked"}`:
  - `transcript.assistant.delta` appends to the last non-final agent line
  - `.done` finalizes it
  - `closed` with `4409` sets error to "Already on a call"
- `useCall(gateway)` returns `{state, dial(roleId), hangup()}`. It wires `startMic` to `sendAudio`, `onAudio` to `player.enqueue`, and `barge_in` to `player.stop()`.
- `CallWindow` is a retro video-call frame: pixel portrait with a talking animation while `speaking`, a waveform, the transcript, task chips, and an `Esc` hang-up button.

- [ ] **Step 1: Write failing tests:**
  - `delta then done builds one agent line`
  - `task.started adds chip`
  - `call.ended sets ended`
  - `4409 sets already-on-call error`
  - `unknown event ignored`: an unrecognized event returns the same state object.
- [ ] **Step 2:** Run `npx vitest run src/call`. Expected: FAIL.
- [ ] **Step 3:** Implement it, with a temporary "Call Michael" button in `App.tsx`.
- [ ] **Step 4:** Run it again. Expected: PASS. Then **Checkpoint 1:** with `VITE_MOCK=0` against A's gateway, call Michael and hold a real voice conversation. Interrupting him stops his audio straight away.
- [ ] **Step 5:** Commit `feat(frontend): call window`.

### Task C5: Office map, movement and desks

**Files:**
- Create: `src/office/{map,movement}.ts`, `src/office/Office.tsx`, `src/office/map.test.ts`, `src/office/movement.test.ts`, `public/sprites/*`

**Interfaces:**
- `map.ts`:
  - `OFFICE_MAP: string[]`: the ASCII tile rows. `#` = wall, `.` = floor, `D` = door, `W` = whiteboard, `R` = reception.
  - `DESK_SPOTS: Record<string, {x, y}>` for `michael_office, accounting, annex, dwight_desk, jim_desk`, plus `AUTO_SPOTS: {x, y}[]`.
  - `layoutDesks(roles: Role[]): Desk[]`, where `Desk = {roleId, x, y}`. A known `desk` gets its spot; others take the next free `AUTO_SPOTS` entry, in the order of `roles`.
- `movement.ts`:
  - `step(pos, dir: "up" | "down" | "left" | "right", desks: Desk[]): Pos`. Blocked by `#`, by `W`, and by desk tiles.
  - `nearby(pos, desks, map): {kind: "desk", roleId} | {kind: "board"} | null` (adjacent within 1 tile)
  - `distance(a, b): number` (Chebyshev)
- `Office.tsx` renders the CSS grid of tiles, the desks with character sprites, and the player. It handles keys per Global Constraints and calls `dial(roleId)`. It auto-hangs-up when `distance(player, activeDesk) > 2`.

- [ ] **Step 1: Write failing tests:**
  - `known desks placed at fixed spots`
  - `unknown role gets auto spot`: a sixth role `{id: "reception", desk: undefined}` lands on `AUTO_SPOTS[0]`.
  - `walls and desks block`
  - `nearby desk detected`
  - `nearby whiteboard detected`
  - `distance chebyshev`
- [ ] **Step 2:** Run `npx vitest run src/office`. Expected: FAIL.
- [ ] **Step 3:** Implement it, and draw the sprites (original pixel art; 16×16 or 32×32, scaled 3×).
- [ ] **Step 4:** Run it again. Expected: PASS. Manual check: walk to Jim's desk, press `E`, and the call opens; walk away and it hangs up.
- [ ] **Step 5:** Commit `feat(frontend): Scranton office map and movement`.

### Task C6: Office state, HUD, toasts and pings

**Files:**
- Create: `src/office/officeReducer.ts`, `src/office/officeReducer.test.ts`, `src/office/Hud.tsx`, `src/results/Toasts.tsx`

**Interfaces:**
- `OfficeState`:
  - `{agents: Record<roleId, "idle" | "working" | "on_call">}`
  - `{bang: Record<roleId, string[]>}`: task IDs with unseen results
  - `{ringing: Record<roleId, boolean>}`
  - `{toasts: {id, text, task_id}[]}`
- `officeReducer(state, action)`, where actions are `ServerEvent`s plus `{type: "opened_result", task_id}` and `{type: "called", roleId}`:
  - `task.completed` adds to `bang[from_role]` and pushes the toast `"<FIRST NAME CAPS>: <title> is done!"` (the first name comes from roles, passed in the initial state)
  - `ping` with `to_role: null` sets `ringing[from_role]`
  - `called` clears `bang` and `ringing` for that role
  - `opened_result` removes that task ID everywhere
- `Hud.tsx` shows the minimap board (counts per column plus the card titles currently in progress) and the toasts. Clicking a toast opens the result viewer.

- [ ] **Step 1: Write failing tests:**
  - `completed adds bang and toast text "DWIGHT: Fix bulk discount is done!"`
  - `null ping rings sender`
  - `called clears bang and ringing`
  - `opened_result clears`
  - `event for unknown role adds entry without throwing`
- [ ] **Step 2:** Run `npx vitest run src/office/officeReducer.test.ts`. Expected: FAIL.
- [ ] **Step 3:** Implement it. Add the cubicle visuals in `Office.tsx`: a glowing monitor for `working`, a "!" sprite, and a phone shake for `ringing`.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(frontend): live office state, HUD and toasts`.

### Task C7: Whiteboard Kanban and result viewer

**Files:**
- Create: `src/board/boardReducer.ts`, `src/board/boardReducer.test.ts`, `src/board/Whiteboard.tsx`, `src/results/ResultViewer.tsx`

**Interfaces:**
- `boardReducer(board: Board, e: ServerEvent): Board`:
  - `task.updated` moves or inserts the card into `columns[status]` and removes it from every other column
  - `resync` is handled in `App` by refetching `/board`
- `Whiteboard.tsx` is a full-screen whiteboard with 6 columns, character-colored cards, and a highlight animation on a card that just moved.
- `ResultViewer.tsx` is framed as a CRT monitor or printout. It calls `fetchTask(id)` and shows the `result_summary`, then each artifact:
  - `diff`: fetches the URL and renders it in a `<pre>`, with `+` lines in green and `-` lines in red
  - `pr`/`link`: an open button
  - `pptx`/`xlsx`: a download button

- [ ] **Step 1: Write failing tests:**
  - `task.updated moves card between columns`
  - `new task inserted`
  - `card never in two columns`
- [ ] **Step 2:** Run `npx vitest run src/board`. Expected: FAIL.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Run it again. Expected: PASS. Manual check with the mock: the card moves `todo → in_progress → done` on the whiteboard and the HUD, the toast appears, and clicking it shows the diff.
- [ ] **Step 5:** Commit `feat(frontend): whiteboard and result viewer`.

### Task C8: Integration, polish and the demo recording (Checkpoint 2 → record)

**Files:**
- Modify: `src/App.tsx`, `styles.css`
- Create: `docs/demo-script.md`

- [ ] **Step 1:** Point at the real gateway (`VITE_MOCK=0`) with `COMPANY_BACKEND=paperclip`. Run the full spec §8 storyline. Fix any contract mismatches with A, against the index rather than by guessing.
- [ ] **Step 2:** Polish:
  - a retro pixel font (from Google Fonts, e.g. "Press Start 2P")
  - a CRT scanline overlay on the call window
  - a title card ("Dunder Mifflin Infinity Voice™")
  - a key-hint bar
- [ ] **Step 3:** Write `docs/demo-script.md`. For each of the 6 storyline beats, record the exact lines the user says, the expected screen state, and the cut points. Between takes, run B's `paperclip/reset_demo.sh`.
- [ ] **Step 4:** Rehearse twice, then record by ~1:30 PM. Use screen recording plus system audio, and keep raw takes so they can be cut.
- [ ] **Step 5:** Commit `feat(frontend): integration polish and demo script`.
