# Product brief: Dunder Mifflin Infinity Voice™

**A company you can call.** Boson AI × MScAC Higgs Audio Hackathon, October 2026. Primary track: **Agents That Act**, also Conversation as the Interface and Put a Face to the Voice.

## The problem

Talking to AI today means typing prompts into a single chatbot. That isn't how people get work done. In a real company:

- For a quick question, you send a message.
- When you want the real picture (how the quarter is going, what's blocking a deal, whether a bug is fixed), **you call someone.** You ask follow-ups, you push back, and they say "I'll look into it" and get back to you.
- Work is divided by **role.** Finance owns the numbers, engineering owns the code, sales owns the pipeline. Each person knows their area, has the access their job needs, and hands work to the right colleague.

One general-purpose assistant flattens all of that. You have to know what to ask, you have to be at a keyboard, and you have to wait while it works. There's also a hard technical limit: real-time voice models are fast but shallow, and anything that needs minutes of real work (fixing code, research, building a deck) breaks the conversation.

## What we built

A simulated company whose employees are AI agents you can phone. We staffed it with the Dunder Mifflin Scranton team from *The Office*, because everyone already knows who does what there.

| Employee | Role | You'd call them to… |
|---|---|---|
| Michael Scott | CEO | get the state of the branch, Q4 targets, what's in the inbox |
| Kevin Malone | CFO | check the P&L, the value of a deal, what the AI staff costs |
| Ryan Howard | Engineering Lead | find out what's broken on the ordering site, and get it assigned |
| Dwight Schrute | Engineer | hear what he's working on right now |
| Jim Halpert | Sales Lead | review the pipeline, get leads researched and pitch decks built |

### The experience

1. **Dial someone.** Pick them from a phone-style contact list, or walk up to their desk in a retro pixel-art office. Choose an audio call or a video call with a lip-synced face.
2. **Just talk.** They answer in character and in real time. Interrupt them and they stop and listen. They already know what's going on in the company, because they're briefed at dial time on open tasks, flags and your last conversation with them.
3. **Ask for real work.** "Have Dwight fix the checkout bug." The task lands on the shared company board, and a background coding agent starts on it.
4. **Keep the conversation going.** Hang up, call someone else, talk about something different.
5. **Get told when it's done.** When the work finishes, whoever you're talking to mentions it in the next natural pause: *"Oh, Dwight just finished the checkout fix. Every test passes."* A toast appears, and one click shows the diff, the pull request, the deck or the PDF.

### What makes it work

- **One employee, two bodies.** Each employee has a *voice body* (a Boson Higgs Realtime session: fast, conversational, interruptible) and a *work body* (a Paperclip agent running Claude Code: slow, thorough, able to change code and produce files). The voice body hands off; the work body delivers.
- **Scoped roles.** Each employee gets only the tools their job needs: the CFO sees financials, sales sees the CRM, engineering sees the code tasks. Every number comes from a tool, never from the model's imagination. A new employee is one config file.
- **Polite interruptions.** The gateway watches each call and slips finished results in only when nobody is speaking and the model isn't mid-reply. It never cuts you off.
- **Teamwork.** Employees delegate to each other. Ryan assigns the fix to Dwight; Michael can hand anything to anyone. Results route back to whoever you're talking to.
- **Research on demand.** Any employee can dig into the outside world (competitors, prospects, markets) on Claude Opus 5.5 and come back with a written brief or a PDF.
- **Visible work.** A live task board, toasts, a result viewer and a Documents panel make the background work easy to follow.

## Who it's for

- **Founders, managers and operators** who want to check in on their business the way they'd check in with their team, in a two-minute call from the car, between meetings, or away from a screen.
- **Teams running AI agents** who need a human-shaped way to supervise them: ask what each one is doing, redirect it, and get notified when it's done.
- **Anyone who'd rather talk than type.** Voice-first means hands-free and eyes-free.

## Beyond The Office

The Office is the fun skin, and it was also a deliberate design test. Its characters are famously difficult, so we wrote them as excellent colleagues who lead with the answer, never stall, and keep the humor to one bit per reply. The same app has a professional mode with the same engine and none of the costume.

A real deployment would:
- **Replace the cast with your team:** a finance agent, an engineering lead, a support lead, an ops analyst, each with its own scope and permissions.
- **Connect real systems** in place of our seeded data: the CRM, the code repo, the ticket tracker, the data warehouse.
- **Put it on a phone line,** so checking in with your company is a phone call from anywhere.
- **Add multi-party calls and agent-to-agent meetings,** with the human as the manager who drops in.

## What's real in the demo

| Real | Seeded or simulated |
|---|---|
| Real-time voice, interruptions, live transcripts (Higgs Realtime + STT) | Company data: financials, CRM, inbox, KPIs, handbook |
| Tool calls against company data, scoped per role | The company itself (a parody of Dunder Mifflin) |
| Delegation creating real tasks on a real task board (Paperclip) | The mock company mode, which fakes finished work with a timer for rehearsals and for anyone without Paperclip |
| Claude Code fixing a real bug in a real repo, running tests and opening a PR | |
| Research on Claude Opus 5.5 with web access; decks and PDFs generated by agents | |
| Lip-synced live avatars (Higgs Avatar) and cloned voices | |

## Technical highlights

- **Server-side voice gateway.** Each browser call (PCM16 at 24 kHz over a WebSocket) is relayed to a Higgs Realtime session the gateway owns, which lets it inject briefings, run tools and time announcements.
- **Quiet-gap injection.** It tracks `response_active` and `user_speaking`, waits about 1.5 s of silence, then inserts a synthetic tool result and asks the model to announce it in character. It never sends `response.create` mid-reply, which under server VAD would interrupt it.
- **Delegation guard.** If the model *says* it will hand something off or look something up but doesn't call the tool, the gateway nudges it to actually do it.
- **Cross-call memory.** Each call is summarized and fed into the next briefing, so Jim knows about the bug you discussed with Ryan.
- **Task completion contract.** A task is done only when its status is `in_review` or `done` *and* the agent posted a `RESULT:` comment. `ARTIFACT:` lines attach diffs, PRs, decks and PDFs.
- **Research on Opus 5.5** through a per-task adapter override on Paperclip.
- **Live avatars** driven by the same realtime audio, which mute on barge-in.
- **Tested:** about 250 Python tests (gateway, company layer, Paperclip seed and skills) plus frontend tests, and an automated end-to-end storyline check (`make scenario`) that plays the user with synthesized speech.

## Built by

Thomas Michalski, Adam Cormier and Paul Ellement. See [the README](../README.md#team) for who built what.
