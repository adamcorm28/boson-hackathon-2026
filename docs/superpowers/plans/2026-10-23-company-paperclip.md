# Company Layer + Paperclip Implementation Plan (Workstream B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dunder Mifflin Scranton exists both as seed data and as a running Paperclip company. Its five agents can be handed work, do it with Claude Code, and report back in a form the gateway can read.

**Architecture:** `backend/company/` is a Python package with one `CompanyAPI` protocol and two implementations. The in-memory mock ships first so the voice gateway never waits. The Paperclip REST client comes later. Paperclip runs locally on Thomas's laptop; agents use the `claude_local` adapter. The Engineer works in a separate demo repo with a seeded bug.

**Tech Stack:** Python 3.11+, httpx, pyyaml, pytest + pytest-asyncio, Paperclip (Node 24.11+), Claude Code, Node's built-in `node:test` for the demo repo, python-pptx, openpyxl.

**Spec:** `docs/superpowers/specs/2026-10-23-voice-company-design.md`. **Index / shared contracts:** `docs/superpowers/plans/2026-10-23-voice-company-index.md`

## Global Constraints

- Shared contract 1 in the index is the API. Never change a signature there without telling A.
- Likeness: personas are text only, with no actor voice clones or photos. Voices: `ceo: marcus`, `engineer: jake`, `sales_lead: oliver`, `eng_lead: default`, `cfo`: whatever A1's findings pick (use `default` until then).
- Persona rules go in every role YAML: excellent at the job and cooperative (personality is flavor, not friction), **lead with the answer**, never refuse/stall/hold back information or let banter affect the work, **at most one comedy bit per reply**, every number and fact comes from tools and is reported accurately, short spoken sentences. Work-body `AGENTS.md` files follow the same rule: in-character tone in comments, flawless work.
- Business facts (exact): about $700k/month sales, 22% gross margin, Q4 goal of beating the Stamford branch. Bulk discount is **10% off orders of 50+ cases**. The Lackawanna County schools contract is worth **about $120k/yr**, blocked by the Infinity bug. David Wallace wants Q4 numbers.
- Reporting lines: `ceo` → {`cfo`, `eng_lead`, `sales_lead`}; `eng_lead` → `engineer`.
- Each role has ≤ 6 voice tools, all drawn from `VOICE_TOOL_NAMES`.
- Paperclip runs in `local_trusted` mode, so the API needs no token.

## Review Focus

- **`get_issue` on an unknown or stale ID** (the model invents one): it should raise `KeyError`, and A turns that into a spoken "can't find that". Test it in B1 and B8.
- **An agent finishes but forgets `RESULT:`, or sets status without commenting:** the watcher must not fire `on_complete`. It waits, and logs once after 10 minutes. Test it in B9.
- **The watcher restarts while tasks are already done** (gateway reload): tasks already complete at the first poll must not be re-announced. Test it in B9.
- **Paperclip is down or slow during a call:** the client raises `CompanyUnavailable` within 3 s instead of hanging the voice turn. Test it in B8.
- **Re-running the seed script:** it must be idempotent, reusing the existing company and agents by name, not making `ceo-2`. Test it in B7.

## File Structure

```
backend/
  pytest.ini                      # asyncio_mode=auto, pythonpath=.
  requirements.txt                # + pyyaml anthropic pytest pytest-asyncio
  company/
    __init__.py                   # get_company()
    types.py                      # shared contract 1
    mock.py                       # MockCompany(CompanyAPI), seeded from data/issues_seed.json
    paperclip.py                  # PaperclipCompany(CompanyAPI)
    results.py                    # parse RESULT/ARTIFACT comments
    watcher.py                    # TaskWatcher
    data_tools.py
    data/ handbook.md kpis.json financials.json crm.json inbox.json issues_seed.json paperclip_ids.json(generated)
  roles/ ceo.yaml cfo.yaml eng_lead.yaml engineer.yaml sales_lead.yaml
  tests/company/ test_mock.py test_data_tools.py test_roles.py test_results.py test_paperclip.py test_watcher.py test_seed.py
paperclip/
  requirements.txt                # python-pptx openpyxl httpx
  seed.py
  reset_demo.sh
  agents/<role>/AGENTS.md
  skills/pitch-deck/{SKILL.md,make_deck.py}  skills/excel-model/{SKILL.md,make_model.py}
  tests/test_skills.py
docs/superpowers/spikes/paperclip-findings.md
../dunder-mifflin-infinity/       # separate git repo
artifacts/                        # gitignored
```

---

### Task B1: Shared types and mock company (push within 45 minutes)

**Files:**
- Create: `backend/company/{__init__,types,mock}.py`, `backend/company/data/issues_seed.json`, `backend/pytest.ini`, `backend/tests/company/test_mock.py`
- Modify: `backend/requirements.txt` (add `pyyaml`, `anthropic`, `pytest`, `pytest-asyncio`), `.gitignore` (add `artifacts/`, `backend/data/`, `backend/company/data/paperclip_ids.json`)

**Interfaces:**
- Produces: everything in shared contract 1 except `data_tools` and `watcher`, plus `MockCompany` with the extra test hook `complete(task_id, summary, artifacts=())`. That hook adds a `RESULT:` comment and sets the status to `done`, so A and C can fake a finished task.
- `issues_seed.json` holds about 10 issues across all roles. It **must** include:
  - "Infinity checkout not applying bulk discount": `assignee_role: eng_lead`, `status: todo`, `flagged: true`
  - "Q4 numbers for David Wallace": `cfo`, `todo`
  - "Lackawanna County quote on hold": `sales_lead`, `blocked`
  - one `done` item and one `in_progress` item

- [ ] **Step 1: Write failing tests** in `test_mock.py`:
  - `test_list_issues_filters_by_role_and_status`: `list_issues(role="eng_lead")` includes the bulk-discount issue; `list_issues(status="blocked")` only returns blocked issues.
  - `test_create_task_marks_voice_origin`: `tid = await c.create_task("engineer", "Fix bulk discount", "brief", "eng_lead")`, then `get_issue(tid)` has `origin == "voice"`, `requested_by_role == "eng_lead"` and `status == "todo"`.
  - `test_get_issue_unknown_raises_keyerror`
  - `test_agent_status_working_when_in_progress`: after `create_task` and a status set to `in_progress`, `get_agent_status("engineer").state == "working"` and `current_task_id == tid`.
  - `test_complete_hook_adds_result_comment`: the last comment body starts with `"RESULT: "` and the status is `"done"`.
  - `test_get_company_defaults_to_mock`: with `COMPANY_BACKEND` unset, it returns a `MockCompany` instance.
- [ ] **Step 2:** Run `cd backend && pytest tests/company/test_mock.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `types.py` exactly as in the index, `MockCompany` (an in-memory dict loaded from `issues_seed.json`, IDs like `DM-101`), and `get_company()` as a process-wide singleton. `MockCompany.get_costs()` returns a fixed `{"total_cents": 412, "by_role": {...}}`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(company): shared types and mock company layer` and **push, then tell A and C.**

### Task B2: Seed data and data tools

**Files:**
- Create: `backend/company/data/{handbook.md,kpis.json,financials.json,crm.json,inbox.json}`, `backend/company/data_tools.py`, `backend/tests/company/test_data_tools.py`

**Interfaces:**
- Produces the `data_tools` functions from shared contract 1:
  - `company_overview()` → `{"branch", "monthly_sales", "gross_margin", "q4_goal", "q4_progress_pct", "headline_kpis": {...}}`
  - `get_pipeline()` → about 15 deals: `[{"account", "value_per_year", "stage", "owner", "blocker"}]`
  - `read_inbox()` → `[{"id", "from", "subject", "snippet", "unread"}]`
  - `read_email(id)` returns the inbox entry plus a `"body"` field.
  - `lookup_company(topic)` matches `##` sections of `handbook.md` by case-insensitive keyword and returns `{"topic", "matches": [{"section", "text"}]}`, with at most 3 matches and each `text` ≤ 600 chars.
- Inbox content must include David Wallace (Q4 numbers), a Lackawanna County escalation, Toby (an HR reminder), and Jan.

- [ ] **Step 1: Write failing tests:**
  - `test_overview_numbers`: `monthly_sales == 700000` and `gross_margin == 0.22`.
  - `test_lackawanna_blocked_by_infinity`: `get_deal("lackawanna")["blocker"]` contains `"bulk discount"` and `value_per_year == 120000`. Matching is case-insensitive and on substrings.
  - `test_get_deal_unknown_returns_none`
  - `test_inbox_has_wallace`: some `from` contains `"David Wallace"`.
  - `test_read_email_unknown_returns_none`
  - `test_lookup_bulk_discount`: `lookup_company("bulk discount")["matches"][0]["text"]` contains `"10%"` and `"50"`.
  - `test_lookup_no_match`: `matches == []`.
- [ ] **Step 2:** Run `pytest tests/company/test_data_tools.py -v`. Expected: FAIL.
- [ ] **Step 3:** Write the data files and `data_tools.py`, loading the JSON once at import.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(company): Dunder Mifflin seed data and data tools`.

### Task B3: Role YAMLs (personas)

**Files:**
- Create: `backend/roles/{ceo,cfo,eng_lead,engineer,sales_lead}.yaml`, `backend/tests/company/test_roles.py`

**Interfaces:**
- Produces files in the spec §6.1 schema. Required keys: `id, name, title, reports_to, paperclip_agent, voice, greeting, persona, voice_tools, can_delegate_to`. Optional keys: `turn_detection, sprite, desk`. A2's loader reads them.
- Desks: `ceo: michael_office`, `cfo: accounting`, `eng_lead: annex`, `engineer: dwight_desk`, `sales_lead: jim_desk`.
- Voice tools:
  - **ceo:** `get_company_overview, read_inbox, read_email, get_board, delegate_task, lookup_company`. `can_delegate_to` = all roles.
  - **cfo:** `get_financials, get_ai_spend, get_board, delegate_task, lookup_company`. `can_delegate_to: [cfo]`.
  - **eng_lead:** `get_my_work, get_board, get_issue, delegate_task, lookup_company, web_search`. `can_delegate_to: [engineer, eng_lead]`.
  - **engineer:** `get_my_work, get_issue, get_board, delegate_task, lookup_company`. `can_delegate_to: [engineer]` (every role can take work directly).
  - **sales_lead:** `get_pipeline, get_deal, get_my_work, delegate_task, web_search, lookup_company`. `can_delegate_to: [sales_lead]`.
- Each `persona` is 8–15 lines. It covers who they are, how they talk, what they care about, how they feel about the others (Dwight vs Ryan, Jim vs Dwight), and the four persona rules from Global Constraints, verbatim.

- [ ] **Step 1: Write failing tests:**
  - `test_all_roles_present`: the set of file stems equals `set(ROLE_IDS)`.
  - `test_required_keys`
  - `test_voice_tools_known_and_max_six`: each set is a subset of `VOICE_TOOL_NAMES` and has length ≤ 6.
  - `test_reports_to_tree`: `engineer → eng_lead`; `cfo`, `eng_lead` and `sales_lead → ceo`; `ceo → null`.
  - `test_delegation_targets_are_roles`
  - `test_persona_has_rules`: each persona contains `"at most one comedy bit"`.
- [ ] **Step 2:** Run `pytest tests/company/test_roles.py -v`. Expected: FAIL.
- [ ] **Step 3:** Write the five YAMLs. Use the spec §6.2 persona notes and the greetings (Michael: "Michael Scott, World's Best Boss. Talk to me."; Ryan: "Ryan here. Let's disrupt something. What do you need?").
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(roles): Dunder Mifflin personas`.

### Task B4: Spike S3, getting Paperclip running (throwaway, no TDD)

**Files:**
- Create: `docs/superpowers/spikes/paperclip-findings.md`

- [ ] **Step 1:** Run `npx paperclipai@latest onboard --yes` (needs Node ≥ 24.11). Confirm `curl -s localhost:3100/api/health` reports healthy.
- [ ] **Step 2:** Save `curl -s localhost:3100/api/openapi.json > /tmp/claude-paperclip-openapi.json`. Record the exact routes for:
  - create/list companies
  - create goal
  - list a company's issues, with filters
  - create agent
  - costs summary
  - agent runs/status
  - issue labels or metadata support
- [ ] **Step 3:** Through the API, create a throwaway `claude_local` agent with `instructionsBundle.files["AGENTS.md"]` saying: "When done, post a comment starting `RESULT:` and set status `done`." Create an issue assigned to it ("Write a haiku about paper"). Time how long it takes to wake up, finish, and post the comment.
- [ ] **Step 4:** Write `paperclip-findings.md` with:
  - the routes from Step 2
  - the observed wake → RESULT latency
  - whether comments carry an author agent ID
  - whether issues support labels/metadata (if not, origin goes in a description footer; see B8)
  - how agent status is best derived
- [ ] **Step 5:** Commit `docs: paperclip spike findings`.

### Task B5: Demo repo `dunder-mifflin-infinity` with the seeded bug

**Files (separate repo at `../dunder-mifflin-infinity/`):**
- `package.json` (`"test": "node --test"`, no dependencies)
- `src/pricing.js`, `src/storefront.js`, `index.html`
- `test/pricing.test.js`
- `README.md`

**Interfaces:**
- `pricing.js` exports:
  - `BULK_THRESHOLD_CASES = 50`
  - `BULK_DISCOUNT = 0.10`
  - `applyBulkDiscount(order) -> number` (the discount in dollars)
  - `quoteOrder({cases, unitPrice}) -> {subtotal, discount, total}`
- **The bug:** `applyBulkDiscount` reads `order.quantity`, but `quoteOrder` passes `{cases, ...}`, so the discount is always 0. The fix is a handful of lines.

- [ ] **Step 1:** Write `test/pricing.test.js`:
  - 60 cases @ 45 → `{subtotal: 2700, discount: 270, total: 2430}`
  - 50 cases @ 45 → `discount: 225`, `total: 2025`
  - 49 cases @ 45 → `discount: 0`, `total: 2205`
- [ ] **Step 2:** Implement `pricing.js` **with the bug** and the storefront page, which shows a quote for a cases input. Run `npm test`. Expected: the 60- and 50-case tests **FAIL** and the 49-case test passes. That's the intended starting state.
- [ ] **Step 3:** Run `git init && git add -A && git commit -m "Dunder Mifflin Infinity storefront" && git tag seeded-bug`.
- [ ] **Step 4:** Check the fix works without committing it: apply it locally, see all 3 tests pass, then run `git checkout .`.

### Task B6: Work-body instructions and skills

**Files:**
- Create: `paperclip/agents/{ceo,cfo,eng_lead,engineer,sales_lead}/AGENTS.md`, `paperclip/skills/pitch-deck/{SKILL.md,make_deck.py}`, `paperclip/skills/excel-model/{SKILL.md,make_model.py}`, `paperclip/requirements.txt`, `paperclip/tests/test_skills.py`

**Interfaces:**
- `make_deck.py <spec.json> <out.pptx>`: the spec is `{"title", "subtitle", "slides": [{"title", "bullets": [str]}]}`.
- `make_model.py <spec.json> <out.xlsx>`: the spec is `{"sheets": [{"name", "rows": [[...]], "formulas": {"B5": "=SUM(B2:B4)"}}]}`.
- Every `AGENTS.md` contains:
  - the character, briefly, so comments read in voice
  - the **RESULT convention** from the index, verbatim
  - the artifact rule: write files to `{ARTIFACTS_DIR}` (absolute path, filled in by B7) and link them as `{GATEWAY_PUBLIC_URL}/artifacts/<file>`
  - "finish in under 3 minutes; prefer a smaller complete result"
- **Engineer extras:**
  - work in `../dunder-mifflin-infinity`, on branch `fix/<slug>`
  - run `npm test` until it passes, then commit
  - write `git diff seeded-bug..HEAD > {ARTIFACTS_DIR}/infinity-fix.diff`
  - link it as `ARTIFACT: diff …`
  - if `gh auth status` succeeds, push and `gh pr create`, then add `ARTIFACT: pr <url>`
- **Sales:** web research, then a 5–6 slide deck with `make_deck.py`. **CFO:** `make_model.py`.

- [ ] **Step 1: Write failing tests:**
  - `test_make_deck_slide_count`: a spec with 3 slides gives a `.pptx` with 4 slides (title + 3). Reopen it with `pptx.Presentation`.
  - `test_make_model_formula_preserved`: reopening with `openpyxl.load_workbook` shows `ws["B5"].value == "=SUM(B2:B4)"`.
  - `test_agents_md_have_result_convention`: every `AGENTS.md` contains `"RESULT:"` and `"ARTIFACT:"`.
- [ ] **Step 2:** Run `pip install -r paperclip/requirements.txt && pytest paperclip/tests -v`. Expected: FAIL.
- [ ] **Step 3:** Implement both scripts and write the five `AGENTS.md` files plus the two `SKILL.md` files. Each `SKILL.md` says when to use the script and shows an example spec.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(paperclip): agent instructions and deck/model skills`.

### Task B7: Seed script

**Files:**
- Create: `paperclip/seed.py`, `backend/tests/company/test_seed.py`

**Interfaces:**
- `async def seed(client: httpx.AsyncClient, *, repo_root: Path, demo_repo: Path, artifacts_dir: Path, gateway_url: str) -> dict`. It returns, and also writes to `backend/company/data/paperclip_ids.json`, the mapping `{"company_id": str, "agents": {role: agent_id}, "issues": {seed_title: issue_id}}`.
- It creates or reuses by name:
  - the company "Dunder Mifflin Paper Company — Scranton", with the goal "Beat Stamford in Q4"
  - the 5 agents, with `name` = character, `adapterType: "claude_local"`, `adapterConfig.cwd` (`demo_repo` for the engineer, `repo_root` for the others) and `reportsTo` per the tree
  - the agents' `instructionsBundle` from `AGENTS.md`, with `{ARTIFACTS_DIR}` and `{GATEWAY_PUBLIC_URL}` substituted
  - every issue in `issues_seed.json`, **unassigned** so seeding wakes no one
- It uses the routes recorded in `paperclip-findings.md`. CLI: `python paperclip/seed.py`.

- [ ] **Step 1: Write failing tests** with `httpx.MockTransport` faking the routes:
  - `test_seed_creates_five_agents_with_reporting_lines`: check the captured POST bodies. The engineer's `reportsTo` equals the eng_lead's ID, and `adapterType == "claude_local"`.
  - `test_seed_is_idempotent`: the transport reports the company and agents as existing. Expect no agent POSTs and the same IDs returned.
  - `test_instructions_placeholders_filled`: no `{ARTIFACTS_DIR}` is left in any posted bundle.
  - `test_seed_issues_unassigned`
- [ ] **Step 2:** Run `pytest tests/company/test_seed.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `seed.py`.
- [ ] **Step 4:** Run it again. Expected: PASS. Then run it for real: `python paperclip/seed.py`. In the Paperclip UI, confirm 5 agents in the right org tree and about 10 issues. **Un-pause the agents** (imports start paused).
- [ ] **Step 5:** Commit `feat(paperclip): idempotent company seed`.

### Task B8: Real Paperclip client

**Files:**
- Create: `backend/company/paperclip.py`, `backend/company/results.py`, `backend/tests/company/test_paperclip.py`, `backend/tests/company/test_results.py`

**Interfaces:**
- `PaperclipCompany(base_url: str, ids: dict, client: httpx.AsyncClient | None = None)` implements `CompanyAPI`. `get_company()` returns it when `COMPANY_BACKEND=paperclip`.
- `CompanyUnavailable` is already in `types.py` from B1. Every HTTP call uses `timeout=3.0` and converts transport errors and 5xx responses to `CompanyUnavailable`.
- Mapping:
  - agent ID ↔ role, via `ids["agents"]`
  - `origin` and `requested_by_role` are stored as a description footer `\n\n---\norigin: voice\nrequested_by: <role>`, unless B4 found labels or metadata. Issues without a footer are `origin: "seed"`.
  - `flagged` = the priority is `critical`/`high`, or the seed title is in the flagged list
  - `create_task` POSTs the issue with `assigneeAgentId` set, which wakes the agent
  - `get_agent_status`: `working` if the role has an `in_progress` issue, with `last_comment` = the newest comment body on it, truncated to 300 chars
- `results.py` provides `parse_result(comments: list[Comment]) -> tuple[str, list[Artifact]] | None`. It finds the **last** comment starting with `RESULT:`. The summary is the text after `RESULT:` up to the first `ARTIFACT:` line. Each artifact comes from an `ARTIFACT: <kind> <url> <label…>` line; lines with an unknown kind or a malformed format are skipped.

- [ ] **Step 1: Write failing tests:**
  - `test_parse_result_summary_and_artifacts`: `"RESULT: Fixed it.\nARTIFACT: diff http://x/a.diff The fix"` → `("Fixed it.", [Artifact("diff", "http://x/a.diff", "The fix")])`.
  - `test_parse_result_none_without_marker`
  - `test_parse_result_skips_bad_artifact_lines`
  - `test_create_task_posts_assignee_and_footer`: the captured body has `assigneeAgentId == ids["agents"]["engineer"]` and a description ending in the `requested_by: eng_lead` footer.
  - `test_list_issues_maps_roles_and_origin`
  - `test_get_issue_404_raises_keyerror`
  - `test_timeout_raises_company_unavailable`: the transport raises `httpx.ConnectTimeout`.
- [ ] **Step 2:** Run `pytest tests/company/test_paperclip.py tests/company/test_results.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement both modules.
- [ ] **Step 4:** Run it again. Expected: PASS. Then run a live smoke check: `COMPANY_BACKEND=paperclip python -c "import asyncio,company;print(asyncio.run(company.get_company().list_issues())[:2])"` from `backend/`.
- [ ] **Step 5:** Commit `feat(company): Paperclip REST client`.

### Task B9: TaskWatcher

**Files:**
- Create: `backend/company/watcher.py`, `backend/tests/company/test_watcher.py`

**Interfaces:**
- Signature as in the index. `poll_once()`:
  - lists voice-origin issues
  - calls `on_update(issue)` when `(status, len(comments))` changed since the last poll
  - calls `on_complete(TaskResult)` exactly once per task when it's complete, per the RESULT convention, using `results.parse_result`
  - **first poll:** tasks that are already complete are recorded as seen and **not** announced
  - catches and logs `CompanyUnavailable`, and keeps polling

- [ ] **Step 1: Write failing tests** with `MockCompany`:
  - `test_complete_fires_once`: `create_task`, then poll (nothing), then `complete(...)`, then poll (one call), then poll (still one).
  - `test_status_done_without_result_does_not_fire`
  - `test_already_complete_at_start_not_announced`
  - `test_update_fires_on_status_change`
  - `test_unavailable_does_not_crash`: a fake company raises `CompanyUnavailable`; `poll_once` returns normally.
- [ ] **Step 2:** Run `pytest tests/company/test_watcher.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement it. `start()` runs `poll_once` every `interval` seconds as an `asyncio` task.
- [ ] **Step 4:** Run it again. Expected: PASS.
- [ ] **Step 5:** Commit `feat(company): task watcher`.

### Task B10: Live loop rehearsal and reset (Checkpoint 2)

**Files:**
- Create: `paperclip/reset_demo.sh`

- [ ] **Step 1:** Write `reset_demo.sh`. It:
  - runs `git -C ../dunder-mifflin-infinity checkout main && git reset --hard seeded-bug` and deletes the `fix/*` branches
  - on GitHub (private repo `thomas-m1/dunder-mifflin-infinity`): closes open PRs (`gh pr close --delete-branch`) and deletes remote `fix/*` branches, so `main` on origin stays at `seeded-bug`
  - empties `artifacts/` and `backend/data/calls/`
  - cancels voice-origin issues through the API
  - re-runs `seed.py`
- [ ] **Step 2:** With the gateway running on `COMPANY_BACKEND=paperclip`, run `create_task("engineer", "Fix Infinity bulk discount", <Ryan's brief>, "eng_lead")`. Time how long until `on_complete` fires. **Target < 3 min.** If it's slower, tighten `engineer/AGENTS.md` (point to `src/pricing.js` and the failing test directly).
- [ ] **Step 3:** Repeat Step 2 for the Sales deck task. Confirm the `.pptx` opens from `http://localhost:8000/artifacts/...`.
- [ ] **Step 4:** Run `reset_demo.sh` and check that the next run starts clean.
- [ ] **Step 5:** Commit `chore(paperclip): demo reset script`.
