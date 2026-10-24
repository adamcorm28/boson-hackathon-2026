# Demo video script: Dunder Mifflin Infinity Voice™

**Length:** 2:45 target, 3:00 hard cap. It's recorded on one laptop and edited from raw takes, and the same video is played during the live presentation ([presentation-script.md](presentation-script.md)).

**The one idea the video has to land:** you get work done by *calling your people*, the same way you would at a real company. You don't type prompts at one chatbot. Each employee has a role, a voice and a face, and only the access their job needs. They hand slow work to each other, keep talking while it runs, and tell you when it's done. The Office is the fun skin on top. The product underneath is a company you can call.

**What every second should prove** (Boson judges real-time voice and tool calling):

| Capability | Where it shows |
|---|---|
| Real-time, natural voice with personality | every call |
| Video calls (Boson live avatars), like Zoom with a colleague | Michael, Jim |
| Interruptions (barge-in) | Jim, beat 4 |
| Tool calls answering from live company data | Michael, Jim |
| Routing: each person knows who owns what | Michael → Ryan → Dwight |
| Delegation to a background Claude Code agent | Ryan → Dwight |
| The conversation continues while the work runs | Jim |
| The result is announced mid-call, in a quiet gap | Jim |
| Real output: a diff with passing tests, a PR, a document | beat 5 |
| Not just The Office: a professional mode, the same engine | beat 1, close |

## Format

- **Voice-over (VO)** only in the cold open, one switch line, and the close. Everywhere else the calls play with their own audio, because the calls are the demo. Record the VO separately and lay it under the B-roll.
- **Lower-third captions** (small, bottom-left, 2 to 3 s each) name what just happened in plain words: *"Live tool call: company financials"*, *"Handed off to Dwight, a Claude Code agent"*. Judges watching with the sound low still follow along.
- **Cuts:** trim dead air, walking and loading, but never cut the ping or the barge-in. They have to feel live, so leave them uncut.
- All calls are made in **classic mode**: faster to dial, contact profiles show each person's scope, and video calls look like a real meeting app. Arcade mode appears in the cold open and on the final frame.

## The beats

User lines in **bold** are what you say. The agents improvise, so expect the gist, not these exact words. Pause about 2 s after each answer, because the gateway only injects news in a quiet gap.

### 0. Cold open (0:00–0:20)
- **Screen:** title card, then the arcade office: idle speech bubbles, the whiteboard HUD.
- **VO:** *"When you need something from your team, you don't write them a prompt. You call them. You ask how things are going, you ask them to dig into something, and they get back to you when it's done. We built a company you can call."*
- Press **M**. The office becomes the classic contact list.
- **VO:** *"The Office is just the costume. Underneath, it's a company of AI employees, each with a role, a voice and their own job to do."*
- **Cut point:** hold the contact list for 1 s, then go straight into the dial.

### 1. Michael (CEO), video call: the state of the branch (0:20–0:50)
1. Click Michael, then **Video**. *"Michael Scott, World's Best Boss. Talk to me."*
2. **"Hey Michael, how's the branch doing?"** He gives monthly numbers and Q4 progress, from tools.
   - Caption: *"Live tool call: company overview and financials"*
3. **"Anything I should worry about?"** He mentions Ryan flagging that Infinity is broken.
   - Caption: *"He knows who owns it: Ryan, Engineering"*
4. Hang up.
- **Cut point:** after his first answer if he runs long. Keep the Ryan line, because it sets up the routing.

### 2. Ryan (Eng Lead), audio call: hand the bug to Dwight (0:50–1:20)
1. Click Ryan; show his contact profile for 1 s (responsibilities, scoped tools), then **Audio**.
   - Caption: *"Every employee only has the tools their job needs"*
2. **"Hey Ryan, what's going on with Infinity?"** Bulk discount not applied on 50+ cases, blocking the Lackawanna County deal (~$120k/yr).
3. **"Okay, have Dwight fix it."** He delegates. A task chip appears in the call.
   - If he only *talks* about delegating: **"Please have Dwight fix the bulk discount bug now."**
   - Caption: *"Handed off to Dwight, a Claude Code agent working on the real repo"*
4. Hang up. Open the board: the blue card ("🎙 from a call") moves to **In progress**. Close it.
- **Cut point:** between "have Dwight fix it" and the board, if the card takes a few seconds to move.

### 3. Jim (Sales Lead), video call: keep talking, then the ping (1:20–2:10)
This is the most important beat, so rehearse it the most.
1. Click Jim, then **Video**. *"Hey, it's Jim."*
2. **"Hey Jim, how's the pipeline looking?"** He starts listing deals from the CRM.
3. **Interrupt him mid-sentence:** **"Actually, just tell me about Lackawanna."** He stops at once and answers. From call memory, he knows about the bug: once it's fixed he'll re-send the quote.
   - Caption: *"Interrupt anytime, like a real conversation"*
4. **"Research five more Scranton-area businesses and build me a pitch deck."** He delegates it (a second chip).
   - Caption: *"Second background task running in parallel"*
5. **Stop talking and wait.** When Dwight finishes, Jim announces it in the next quiet gap: the checkout fix is done and every test passes.
   - **Screen:** the toast slides in at the bottom right. Caption: *"Dwight finished, and the news came to you mid-call"*
- **Timing:** Dwight's fix targets under 3 minutes from the hand-off. If it hasn't landed, keep chatting with Jim about the deal and cut the wait in the edit (cut *before* his announcement, never into it).

### 4. The work is real (2:10–2:30)
1. Hang up and click the toast. The result viewer shows the RESULT summary "by Dwight Schrute" and the diff (green and red lines), plus **Open PR**. Hold 3 s on the diff.
   - Caption: *"A real fix, real tests and a real pull request, made by Claude Code"*
2. Press **F** for Documents: Jim's deck (or a research PDF), opened for 2 s.
- **Timing:** the deck takes longer than the fix. Record it after it lands and cut it in.

### 5. Close (2:30–2:45)
- **Screen:** press **M** back to the arcade office, or end on the classic contact list with every task Done on the board.
- **VO:** *"Same idea, any company. Swap the characters for your real team, put it on your phone, and check in with your engineers, your finance lead or your sales team while you're on the road. No typing, no dashboards: you just call."*
- **Final frame:** the whiteboard with everything done, and the title card: **Dunder Mifflin Infinity Voice™ · Boson Higgs Realtime + Claude Code**. Fade out.

## If the cut runs long
In order: shorten Michael to one answer, drop Ryan's profile shot, drop the deck from beat 4. Never drop the barge-in or the ping.

## Before recording

**Machine** (the laptop that runs Paperclip):
- [ ] `make paperclip-status` says up, and `backend/.env` has `COMPANY_BACKEND=paperclip`.
- [ ] `make up` (Paperclip, gateway :8000, frontend :5173). Open http://localhost:5173.
- [ ] `cd frontend && npm run check:gateway` passes (uses no Boson credits).
- [ ] Chrome: mic permission for `localhost:5173` already granted (click through one call first), notifications off, bookmarks bar hidden, full screen.
- [ ] Classic mode in the light scheme (it reads better on a projector); switch it before the first take.
- [ ] **Headphones on.** Through speakers, the agents hear themselves and stop mid-sentence.
- [ ] Pre-warm Dwight: run one throwaway fix before the first take (then reset), so Claude Code isn't cold on camera.
- [ ] Do one video call before recording, so the avatar picture loads quickly on camera.

**Recording:** OBS with a display capture, Chrome's audio, and your mic as a separate track, so the volumes can be balanced in the edit. 1080p, 30 fps. Keep every raw take.

## Reset between takes

1. `make reset-demo`: Paperclip tasks, runs and sessions, the demo repo, GitHub PRs and branches, artifacts and call logs, then a re-seed.
2. Restart `make up` (clears queued results), then reload the browser tab.

**Fallback if Paperclip misbehaves:** run with `COMPANY_BACKEND=mock SIMULATE_WORK_SECONDS=45` (`make up-mock`). Everything on screen looks the same, and delegated tasks "finish" after 45 s with a summary but no real diff. Use this only if the real run fails twice, and then don't show the diff in beat 4.

## If something goes wrong on camera

| Problem | Do this |
|---|---|
| "Mic blocked — allow microphone and retry" | Allow the mic in Chrome's address bar, click **Retry mic**. Re-take the beat. |
| The call window says "Already on a call" | A call is still open in another tab or `talk.py`. Close it and redial. |
| The agent stops mid-sentence by itself | It's hearing the speakers: headphones. |
| The avatar shows initials and no picture | Wait 2 s, or redial as audio and use video only for Jim. |
| A call ends by itself ("idle timeout") | Boson closes sessions after 5 min of silence. Redial. |
| The board looks stale after a restart | It refetches on reconnect; reload the tab if not. |
| Ryan won't delegate | The fallback line in beat 2. |
