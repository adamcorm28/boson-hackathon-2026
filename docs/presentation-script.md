# Live presentation: Dunder Mifflin Infinity Voice™

**Slot:** 10 minutes including Q&A. The demo itself is the recorded video ([demo-script.md](demo-script.md)); nothing runs live on stage.

| Time | Section | Who |
|---|---|---|
| 0:00–1:15 | 1. Why call your company? | speaker 1 |
| 1:15–4:15 | 2. The demo video (3:00) | play it; nobody talks over it |
| 4:15–6:00 | 3. How it works | speaker 2 |
| 6:00–6:45 | 4. Beyond The Office | speaker 1 |
| 6:45–10:00 | 5. Q&A | everyone (owners below) |

Each section's script is what to *say*, kept short enough to deliver from memory. Keep the timings and drop words, not sections. If you're running late, cut section 3 down to the diagram and its first two points.

## 1. Why call your company? (0:00–1:15)

> Think about how you actually get things done at work. For a quick question, you send someone a message on Slack or Teams. But when you want the real picture (how the quarter's going, what's blocking a deal, whether something's fixed), you **call someone**. You talk, you ask follow-ups, they tell you they'll look into it, and later they get back to you.
>
> AI assistants today are one chatbot you type prompts into. That's not how a company works. A company is people with **roles**: someone owns the finances, someone owns the code, someone owns sales. They know their area, they have access to what their job needs, and they hand work to each other.
>
> So we built a company you can call. Every employee is an AI agent with a role, a personality, a voice, and a face. You call them, talk to them in real time, interrupt them, ask them to do things. When it's slow work, they hand it to a background agent and **keep talking with you**. And when it's done, they tell you, even if you're on a call with someone else.
>
> We dressed it up as Dunder Mifflin from *The Office*, because everybody already knows who does what there. Let's go meet the team.

**Slide:** the title card, or a screenshot of the arcade office.

## 2. The demo video (1:15–4:15)

Play it full screen with sound. Don't narrate over it: the captions carry it. If the room's audio is poor, pause once after the ping and say one line: *"Notice: Dwight finished while I was talking to Jim, and Jim told me."*

## 3. How it works (4:15–6:00)

**Slide:** one diagram: browser → voice gateway → Higgs Realtime, and gateway → company layer → Paperclip → Claude Code agents, with the result coming back.

> **One employee, two bodies.** Every employee has a *voice body* and a *work body*.
>
> The voice body is a live **Boson Higgs Realtime** session. It's fast and conversational, and you can interrupt it. Before each call, it's briefed on the live state of the company: open tasks, flags, what you talked about last time. It answers from **tool calls** against company data, so every number comes from a tool, not from the model's imagination. Each role gets a handful of tools, scoped to its job: the CFO sees the financials, the engineer sees the code tasks.
>
> The work body is a **Paperclip agent running Claude Code**. When you ask for something that takes real work (fix a bug, research leads, build a deck), the voice body creates a task on the company board and the work body picks it up. Dwight's fix in the video was real: Claude Code on a real repo, real tests, and a real pull request. Research questions run on **Claude Opus 5.5** and come back as a written brief or a PDF.
>
> The tricky part is **getting the result back into a live conversation without being rude**. Our gateway watches the call. When nobody's speaking and the model isn't answering, it slips the result in as a tool output, and the employee tells you in their own words. It never cuts you off mid-sentence.
>
> Video calls use **Boson's live avatars**, lip-synced to the same voice, and they go quiet the instant you interrupt.
>
> Roles are modular. A new employee is **one config file** (persona, voice, tools, responsibilities) plus one Paperclip agent.

## 4. Beyond The Office (6:00–6:45)

**Slide:** classic mode next to the arcade office, captioned "same engine, two skins".

> The Office is the fun layer. Underneath, the characters are excellent, cooperative employees, and that's the actual product: **a company you can talk to.** You saw the professional mode in the video, and it's the same engine. Swap the characters for your real team and connect real tools: your CRM, your repo, your ticketing system. Put it on a phone line, and you can check in with engineering, finance or sales from the car. You don't need a screen or typing, and nobody needs to be at their desk. You just call, and they get back to you.

**Close:** *"That's Dunder Mifflin Infinity Voice. Thanks! We're happy to take questions."*

## 5. Q&A (6:45–10:00)

Answer in two sentences, then stop. The owner answers; anyone else adds at most one line.

| Likely question | Answer | Owner |
|---|---|---|
| Why voice instead of a chat window? | A call is how people already get updates and give instructions, and it works when you're away from a screen. Real-time voice with interruptions feels like talking to a colleague, not filling in a form. | speaker 1 |
| Why many agents instead of one? | Roles give each agent a narrow scope: their own tools, their own data and their own responsibilities. That keeps answers grounded and makes it obvious who to ask. It's also how you'd limit access in a real company. | speaker 2 |
| How do you stop it from making up numbers? | Every number comes from a tool call against company data, and the personas are told never to guess. The briefing tells each agent what's live at the start of the call. | speaker 2 |
| What's real and what's mocked? | The company data (financials, CRM, inbox) is seeded for the demo. The voice, the tool calls, the delegation and the work are all real: Claude Code really fixed the bug and opened the PR, and research really runs on Opus 5.5. | speaker 2 |
| How does the result interrupt a call without being rude? | The gateway tracks whether you're speaking and whether the model is answering. It waits for a quiet gap of about 1.5 s, then injects the result as a tool output and lets the employee say it in their own words. | speaker 2 |
| Can agents talk to each other? | Yes. Any employee can delegate to another: Ryan assigned the fix to Dwight, and Michael can hand work to anyone. The results route back to whoever is on the call with you. | speaker 2 |
| How long does background work take? | It depends on the task: in the video, the bug fix took a few minutes and the deck longer. You keep talking in the meantime. | speaker 2 |
| What does it cost? | Kevin, the CFO, can tell you: he has a tool that tracks the AI staff's spend, estimated at API list prices. *(Give the real figure from a rehearsal run here, or skip the number.)* | speaker 2 |
| Did you clone the actors' voices? | No. The characters are text personas only. The voices are Boson presets and the faces are original art or Boson's preset avatars. | speaker 1 |
| What would it take to use this for a real company? | Replace the seed data with connectors to real systems, write one config file per role, and add auth and a phone line. The architecture doesn't change. | speaker 1 |
| What was hardest? | Getting results into a live call at the right moment, and making the voice agents actually call the delegate tool instead of just *saying* they would. We added a nudge for that. | speaker 2 |

## Before you present

- [ ] The video file is on the presenting laptop *and* on a USB stick, and it plays with sound through the room's speakers.
- [ ] Three slides: title, architecture diagram, "same engine, two skins". No other slides.
- [ ] Each speaker has rehearsed their section to time, twice.
- [ ] Assign the speakers (suggestion: speaker 1 tells the story and handles product questions; speaker 2 covers the architecture and technical questions; anyone else gets the Q&A rows for their own part, e.g. avatars or the frontend).
