# Gateway dev tools

Rehearse calls without Paperclip or the frontend. Everything runs against the mock company. With `SIMULATE_WORK_SECONDS` set, delegated tasks "finish" after that many seconds, which drives the same board, status and ping events the real Paperclip agents will.

Run these from `backend/`. Install once with `.venv/bin/pip install -r requirements-dev.txt`.

## Talk to an agent yourself
```bash
SIMULATE_WORK_SECONDS=30 .venv/bin/uvicorn main:app --port 8000     # terminal 1
.venv/bin/python dev/talk.py eng_lead                               # terminal 2 (Ctrl+C hangs up)
```
- **Roles:** `ceo` (Michael), `cfo` (Kevin), `eng_lead` (Ryan), `engineer` (Dwight), `sales_lead` (Jim).
- **Without headphones,** the mic mutes while the agent talks, so they don't hear themselves. With headphones, add `--full-duplex` so you can interrupt them. Using `--full-duplex` through speakers makes the agent cut itself off after every word: it hears its own voice as you interrupting. The browser frontend doesn't have this problem, because browsers cancel echo automatically.
- **Try the demo loop:** ask Ryan to have Dwight fix the Infinity bulk discount. Hang up, then call Jim and chat. About 30 s after the delegation, Jim tells you Dwight is done.
- **Watch the screen:** transcripts, `[tool]` calls, `[board]` moves, `[done]` results and `[ping]`s print live.
- **Finish a task by hand,** if you don't want to wait: `curl -X POST localhost:8000/dev/complete/DM-111`

## Automated storyline check
```bash
.venv/bin/python dev/scenario.py            # starts its own gateway on :8001, about 2.5 min
```
It plays the user with TTS speech. Ryan delegates to Dwight, then Jim announces Dwight's finished fix mid-call. At the end it prints a PASS/FAIL checklist. The default is `--work-seconds 45`, because the hang-up and redial take about 30 s.

## One scripted call
```bash
.venv/bin/python dev/call_client.py ceo "How's the branch doing?"
STAY=40 .venv/bin/python dev/call_client.py sales_lead "Hey Jim, how's the pipeline?"
```

## Lip-synced faces from photos
```bash
.venv/bin/python dev/set_avatar.py ~/Downloads/dwight.jpg                  # role from the file name
.venv/bin/python dev/set_avatar.py ~/Downloads/friend.png --role engineer   # or say which employee
make avatar PHOTO=~/Downloads/friend.png FOR=engineer                       # same, from the repo root
```
It copies the photo to `data/avatars/<role>.<ext>` (an earlier one moves to `data/avatars/old/`), takes that role off the Boson live avatar in `data/live_avatars.yaml`, and renders the idle loop (~10 s). Then refresh the browser tab; the gateway needs no restart. Use your own photo, a teammate who agreed, or drawn art, never an actor's photo.

## Cloned voices on this machine
Put `role_id: voice_<id>` lines in `backend/data/voice_overrides.yaml`. It overrides the voice in `backend/roles/*.yaml`, and is read when the gateway starts. Clones belong to one Boson account, so they stay out of the shared role files.
