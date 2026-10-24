# Dunder Mifflin Voice Company

Call the AI employees of a (parody) Dunder Mifflin Scranton in a retro office. Calls run on Boson's Higgs Realtime, and longer work is handed to Paperclip agents running Claude Code. Design: [docs/superpowers/specs/2026-10-23-voice-company-design.md](docs/superpowers/specs/2026-10-23-voice-company-design.md).

Run `make` to list the common commands.

## Quick start (mock company, no Paperclip)

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # set BOSON_API_KEY
cd .. && make gateway
```

`COMPANY_BACKEND=mock` (the default) uses in-memory seed data. To fake an agent finishing a task, call `MockCompany.complete(task_id, "summary")`.

## Full local setup (your own Paperclip and agents)

```bash
make setup        # = scripts/setup_local.sh
```

The script is safe to re-run. It:
- creates `backend/.venv` and `paperclip/.venv`
- clones the private demo repo `thomas-m1/dunder-mifflin-infinity` next to this one
- starts a local Paperclip at http://127.0.0.1:3100, in the background, with its log at `~/.paperclip/dev-server.log`
- seeds Dunder Mifflin: five agents, an org chart and 10 tasks

Then set `COMPANY_BACKEND=paperclip` in `backend/.env`.

**Before you run it:**
- Node ≥ 24.11, Python ≥ 3.11, git.
- **Claude Code installed and logged in.** Agents run on *your* Claude login, so their work uses your subscription.
- **Collaborator access to `thomas-m1/dunder-mifflin-infinity`**, then `gh auth login`. Ask Thomas.

Each teammate gets their own separate company and board. The recorded demo runs on one laptop.

**Day to day:**
- `make paperclip-status`, `make paperclip-start`, `make paperclip-stop`, `make paperclip-logs`
- `make seed` re-seeds after editing personas, `AGENTS.md` or seed data.
- `make reset-demo` does a full reset between takes: Paperclip tasks, runs and agent sessions, the demo repo, GitHub PRs and branches, artifacts and call logs, then re-seeds. `make reset-repo` only resets the demo repo.

## Tests

```bash
make test         # or make test-backend / make test-paperclip
```
