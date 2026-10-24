# Demo script: Dunder Mifflin Infinity Voice™

Five minutes, recorded on one laptop, edited from raw takes. Storyline: spec §8. Record by about 1:30 PM Saturday, after two rehearsals.

You play "corporate", visiting the Scranton branch. You walk your character to an employee's desk and press **E** to call them. You talk to them, and the slow work happens in the background (Paperclip + Claude Code).

## Before recording

**Machine** (the laptop that runs Paperclip):
- [ ] `make paperclip-status` says up. `backend/.env` has `COMPANY_BACKEND=paperclip`.
- [ ] Gateway running: `make gateway` (port 8000).
- [ ] Frontend running against it: `cd frontend && npm run dev` (not `dev:mock`), open http://localhost:5173.
- [ ] `cd frontend && npm run check:gateway` passes (REST, events, call socket; it uses no Boson credits).
- [ ] Chrome: mic permission for `localhost:5173` already granted (click through one call before recording), notifications off, bookmarks bar hidden, full screen.
- [ ] **Headphones on.** Through speakers, the agents hear themselves and stop mid-sentence.
- [ ] Pre-warm Dwight: run one throwaway fix before the first take (then reset), so Claude Code isn't cold on camera.

**Recording:** OBS with a display capture, Chrome's audio (macOS 13+ captures app audio), and your mic as a separate track, so the volumes can be balanced in the edit. 1080p, 30 fps. Keep every raw take.

**Office life:** the idle speech bubbles and the jello add life to the establishing shot. If they distract in a take, press **Q** to turn them off.

## Reset between takes

1. `make reset-repo`: the demo repo goes back to the seeded bug.
2. Once B10 lands, also run `paperclip/reset_demo.sh`. It closes PRs, empties `artifacts/` and `backend/data/calls/` (call memory), cancels voice tasks and re-seeds. Until then: `make seed`, then delete `backend/data/calls/` by hand.
3. Restart the gateway (clears queued results), then reload the browser tab: the title card is back, and the office is at the entrance.

**Fallback if Paperclip misbehaves:** run the gateway with `COMPANY_BACKEND=mock SIMULATE_WORK_SECONDS=45`. Everything on screen looks the same, and delegated tasks "finish" after 45 s with a summary but no real diff. Use this only if the real run fails twice.

## Where everyone sits

You start at the entrance on the left (by reception).

| Who | Where | Stand here |
|---|---|---|
| Michael | his office, top-left (door on its right wall) | inside, next to his desk |
| Jim & Dwight | facing desks, middle of the bullpen | left of Jim's desk / right of Dwight's |
| Kevin | accounting corner, bottom-left | right of his desk |
| Ryan | the annex, bottom-right (door on its left wall) | inside, left of his desk |
| Whiteboard | conference room, top-right (door on its left wall) | under the board |

Walking more than 2 tiles from someone's desk hangs up, so don't wander during a call.

## The six beats

User lines in **bold** are what you say. The agents improvise, so expect the gist rather than these exact words. Pause about 2 s after each answer: the gateway only injects news in a quiet gap.

### 0. Cold open (≈10 s)
- **Screen:** title card, "DUNDER MIFFLIN · INFINITY VOICE™". Hold 3 s, press **Enter**.
- Walk from the entrance toward Michael's office. Viewers see the HUD (mini-whiteboard) on the right and someone's speech bubble.
- **Cut point:** start of the walk; trim the rest of it.

### 1. Michael: the state of the branch (≈50 s)
1. At Michael's desk, press **E**. *"Michael Scott, World's Best Boss. Talk to me."*
2. **"Hey Michael, how's the branch doing?"** He gives the monthly numbers and Q4 progress (from tools), plus at most one tangent.
3. **"Anything I should worry about?"** He mentions Ryan flagging that Infinity is broken, and David Wallace's email about Q4.
4. **Esc** to hang up.
- **Screen:** call window with Michael's portrait animating, the live transcript, and the waveform.
- **Cut point:** after his first answer if it runs long; keep the "Ryan flagged Infinity" line.

### 2. Ryan: the bug, and the hand-off to Dwight (≈60 s)
1. Walk to the annex (bottom-right), press **E** at Ryan's desk. *"Ryan here. Let's disrupt something. What do you need?"*
2. **"Hey Ryan, what's going on with Infinity?"** The checkout doesn't apply the 10% bulk discount on 50+ cases, and that's blocking the Lackawanna County schools deal (~$120k/yr).
3. **"What do you recommend?"** Have Dwight fix it.
4. **"Okay, do it."** He delegates to Dwight.
   - If he only *talks* about delegating: **"Please have Dwight fix the bulk discount bug now."**
5. Hang up.
- **Screen:** a task chip appears in the call ("📋 … → Dwight"). After hanging up, press **B**: the new blue card ("🎙 from a call") is in To do, then moves to **In progress** with an orange highlight. Dwight's monitor glows in the office. **Esc** closes the board.
- **Cut point:** between "Okay, do it" and the board, if the card takes a few seconds to move.

### 3. (Optional) Dwight: what are you doing right now? (≈25 s)
1. Right of Dwight's desk, press **E**. *"Dwight Schrute. Engineer. State your business."*
2. **"Dwight, what are you working on right now?"** Live run status ("root cause found, tests running"), plus a beet fact.
3. Hang up.
- **Screen:** Dwight's glowing monitor, his card in progress on the HUD.
- **Cut point:** the whole beat is optional; drop it if the take runs over 5 min.

### 4. Jim: the pipeline, and the ping mid-call (≈75 s)
1. Left of Jim's desk, press **E**. *"Hey, it's Jim."*
2. **"Hey Jim, how's the pipeline looking?"** Top deals from the CRM.
3. **"What about Lackawanna County?"** From call memory, he knows about the bug: once it's fixed, he'll re-send the quote.
4. **"Research five more Scranton-area businesses and build me a pitch deck."** He delegates it (a second chip appears).
5. **Stop talking and wait.** When Dwight finishes, Jim announces it in the next quiet gap: Dwight's fix is done and every test passes.
- **Screen:** the toast **"DWIGHT: <task> is done!"** slides in at the top-right. A **"!"** appears over Dwight. His phone does *not* ring, because the news was delivered inside Jim's call.
- **Timing:** Dwight's fix targets under 3 minutes from the hand-off in beat 2. If it hasn't landed, keep chatting with Jim about the deal; cut the wait in the edit.
- **Cut point:** between the pitch-deck request and the announcement.

### 5. The result, and (optionally) Kevin (≈45 s)
1. Hang up, then click the toast (or open the board with **B** and click Dwight's card).
2. **Screen:** the CRT result viewer shows the RESULT summary, "by Dwight Schrute", and the diff, with added lines green and removed lines red. If `gh` was authenticated, an **Open PR** button too. Hold 4 s on the diff, then **Esc**.
3. Optional Kevin, in the accounting corner (bottom-left): **"Kevin, what's Lackawanna County worth to us?"** then **"What did today's AI work cost?"** Numbers from tools: today's agent work, estimated at API list prices.
- **Cut point:** before Kevin, if time is short.

### 6. Close: everything done (≈20 s)
1. When Jim's deck finishes (a second toast, from Jim), click it. The viewer shows **Download deck**; open the `.pptx` for 2 s if time allows.
2. Walk into the conference room and press **E** under the whiteboard (or press **B**). Both voice cards are in **Done**.
- **Final frame:** the whiteboard with everything done. Fade out.
- **Timing:** the deck takes longer than the fix. Record this beat after it lands and cut it in.

## If something goes wrong on camera

| Problem | Do this |
|---|---|
| "Mic blocked — allow microphone and retry" | Allow the mic in Chrome's address bar, click **Retry mic**. Re-take the beat. |
| The call window says "Already on a call" | A call is still open in another tab or `talk.py`. Close it and redial. |
| The agent stops mid-sentence by itself | It's hearing the speakers: headphones. |
| A call ends by itself ("idle timeout") | Boson closes sessions after 5 min of silence. Redial. |
| The board looks stale after a gateway restart | It refetches on reconnect; reload the tab if not. |
| Ryan won't delegate | The fallback line in beat 2. Then `curl -X POST localhost:8000/dev/complete/<id>` (mock only) to rehearse the rest. |
