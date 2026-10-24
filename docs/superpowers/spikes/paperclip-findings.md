# Paperclip spike findings (B4 / S3)

Run 2026-10-23 on Thomas's laptop: Paperclip from `npx paperclipai@latest`, Node v24.13.0, Claude Code 2.1.288.

## Setup

- Install and start: `PAPERCLIP_TELEMETRY_DISABLED=1 npx -y paperclipai@latest onboard --yes --no-install-service`, run from `~`.
  - This runs in the foreground, so keep the terminal open.
  - It prints `EBADENGINE` warnings because some dependencies want Node ≥ 24.15. They're harmless.
- Resulting instance:
  - mode `local_trusted`, bound to `127.0.0.1:3100`, embedded Postgres on `:54329`
  - UI at http://127.0.0.1:3100, API at http://127.0.0.1:3100/api
  - config in `~/.paperclip/instances/default/`
- **The API needs no token** in this mode.
- The full OpenAPI document is at `GET /api/openapi.json` (815 paths).

## Routes we need (verified)

| Purpose | Route | Notes |
|---|---|---|
| Health | `GET /api/health` | |
| Create / list companies | `POST` / `GET /api/companies` | body `{name, description?, budgetMonthlyCents?}`. The reply has `id` and `issuePrefix` (derived from the name, e.g. `SPI`) |
| Delete company | `DELETE /api/companies/{companyId}` | |
| Create / list goals | `POST` / `GET /api/companies/{companyId}/goals` | body `{title*, description, level: company\|team\|agent\|task, status: planned\|active\|achieved\|cancelled, ownerAgentId}` |
| Create / list agents | `POST` / `GET /api/companies/{companyId}/agents` | see "Agents" below |
| Get / update agent | `GET` / `PATCH /api/agents/{id}` | |
| **Resume agent** | `POST /api/agents/{id}/resume` (body `{}`) | **New agents are created `paused`. Resume each one or it never runs.** |
| Pause agent | `POST /api/agents/{id}/pause` | |
| Agent runtime | `GET /api/agents/{id}/runtime-state` | `lastRunStatus`, token totals, `sessionId` |
| Create issue | `POST /api/companies/{companyId}/issues` | body `{title, description, status, priority, assigneeAgentId, labelIds?, parentId?, blockedByIssueIds?}`. **Setting `assigneeAgentId` wakes the agent immediately.** |
| List issues | `GET /api/companies/{companyId}/issues` | The only query param is `view=compact`; **filter by role or status on the client side** |
| Get / update issue | `GET` / `PATCH /api/issues/{id}` | the PATCH accepts `status`, `assigneeAgentId`, `comment`, `priority`, `labelIds` and more |
| Comments | `GET` / `POST /api/issues/{id}/comments` | the POST body is `{body*}` |
| Runs for an issue | `GET /api/issues/{id}/runs` | run fields include `runId`, `status` (`succeeded`…), `startedAt`, `finishedAt`, `agentId`, `usageJson` |
| Labels | `GET` / `POST /api/companies/{companyId}/labels` | issues carry `labelIds` and `labels` |
| Costs | `GET /api/companies/{companyId}/costs/by-agent`, `.../costs/summary` | see "Costs" below |

## Agents

- `POST /api/companies/{cid}/agents` with:
  - `{name, role, title, adapterType: "claude_local", adapterConfig: {cwd}, instructionsBundle: {files: {"AGENTS.md": "..."}}, reportsTo?}`
- `role` must be one of `ceo, cto, cmo, cfo, security, engineer, designer, pm, qa, devops, researcher, general`. Our mapping:
  - CEO → `ceo`
  - CFO → `cfo`
  - Eng Lead → `cto`
  - Engineer → `engineer`
  - Sales Lead → `general`, with title "Sales Lead"
- The reply has `id` and `urlKey` (a slug of the name, e.g. `spike-poet`). `shortname` is `null`; use `id` or `urlKey`.
- `claude_local` used Thomas's **Claude subscription login** automatically (the run was reported as `subscriptionRunCount: 1`). No API key was needed.
- The default `runtimeConfig.heartbeat.enabled` is `false`, so agents **only wake on assignment or comments**, never on a timer. Seeded issues that aren't assigned to anyone cost nothing.

## Observed latency

On the throwaway task "Write a haiku about paper":
- **Assignment to run start: about 0.1 s.**
- **Run start to the `RESULT:` comment and status `done`: about 29 s.**
- **Total: about 31 s.**

## RESULT convention works as designed

- The agent posted exactly:
  ```
  RESULT: Wrote a 5-7-5 haiku about paper for SPI-1.
  ARTIFACT: link https://example.com Example
  <blank line + extra content>
  ```
- It then set the status to `done`.
- Comments carry `authorType: "agent"` and `authorAgentId`, so we can map authors back to roles.
- **For B8:** a `RESULT:` comment may continue past the `ARTIFACT:` lines, as here, so the parser must stop at the first line that is neither of those.

## Origin tagging

- The description footer `\n\n---\norigin: voice\nrequested_by: <role>` round-trips unchanged.
- Labels also exist (`labelIds`), but the footer is proven and needs no setup. **Decision: keep the footer.**

## Gotchas and impacts on later tasks

- **JSON with raw control characters.** Some API replies (for example the reply to issue creation, whose description contains newlines) **don't parse with strict JSON**. In B8, parse with `json.loads(resp.text, strict=False)`, not `resp.json()`.
- **Costs are $0 on a subscription.** `costCents`/`spendCents` were 0 because the run was billed to the Claude subscription. `by-agent` still reports `inputTokens`, `cachedInputTokens` and `outputTokens`.
  - For Kevin's `get_ai_spend` (B8 `get_costs`), compute an **estimate** from tokens at API list prices and label it "estimated".
  - Alternatively, report the token counts directly.
- **B7 seed:** after creating each agent, call `POST /api/agents/{id}/resume`.
- **B8 status:** use the agent's `status` (`idle` or running), or an `in_progress` issue assigned to the role, to derive `AgentStatus`. `GET /api/issues/{id}/runs` gives run timing.

## Learned while seeding (B7)

- **`in_progress` needs an assignee.** Creating an unassigned issue with `status: in_progress` fails with `400 in_progress issues require an assignee`. `blocked`, `done` and `in_review` are fine unassigned.
- **New agents auto-ready.** They are created `paused`, then move to `idle` (`lifecycleState: ready`) by themselves within a few seconds. `POST /resume` on an agent that isn't paused returns `409`; treat that as success.
- **Instructions have their own endpoint.** `PATCH /api/agents/{id}` with `instructionsBundle` returns `409 Unsupported configuration field`. To update `AGENTS.md`:
  1. `GET /api/agents/{id}/instructions-bundle/file?path=AGENTS.md`, which returns `content`, `contentHash` and `revision.id`
  2. `PUT /api/agents/{id}/instructions-bundle/file` with `{path, content, baseRevisionId: revision.id}`. Without `baseRevisionId` it returns `422 INSTRUCTION_BASE_REQUIRED`.
- **The issue prefix comes from the company name** and can't be set. Ours is `DUNA` because another company already holds `DUN`. Seed IDs (`DM-101`…) map to Paperclip IDs through `paperclip_ids.json` → `issues`.

## Dry runs (B10, 2026-10-24 ~01:30 EDT)

| Run | Time to RESULT | Notes |
|---|---|---|
| Dwight fixes the bulk-discount bug | **51 s** | Root cause found, one-line fix, 4/4 tests, real PR + diff |
| Jim researches 5 prospects + deck | **130 s** | 6-slide `.pptx` + research brief with sources |
| Dwight again, after `make reset-demo` | **12.8 min** | Fresh session (reset works); every model call took 2–3 min, see below |
| Kevin smoke task | 33 s, later 91 s | Same tiny task, different API latency |

- **API latency spikes are external.** In the slow run, the transcript shows 23 small model calls (86–718 output tokens each). The first ones returned in seconds, then each took 2–3 minutes with no errors logged. A standalone `claude -p` call right afterwards returned in 7 s. Nothing in our code or Paperclip caused it.
  - **For the recording:** run Dwight's fix as its own take, retake if it's slow, and cut the waiting in the edit.
- **Paperclip's bundled Claude Code is 2.1.257**, not the system install. It **rejects `claude-opus-5-5`** (`400 … version 2.1.280 or newer is required`), and its `opus` default resolves to `claude-opus-5`. The seed now pins `adapterConfig.model = claude-opus-5` (`AGENT_MODEL` overrides it).
- **A failed run leaves the task waiting.** That run failed with `errorCode: acpx_turn_failed`, but no RESULT comment was posted, so the watcher just keeps waiting. It doesn't detect failed runs.
- **Pricing (live page, 2026-10-24), per MTok as input / cache hits / output:**
  - Opus 5: $5 / $0.50 / $25
  - Opus 5.5: $4 / $0.20 / $20
  - Sonnet 5.5: $2 / **$0.10** / $10 (the cached skill table said $0.20)
  - Fable 5.1: $10 / $0.25 / $50
- **Cost observed:** one trivial Kevin task came to about 300k tokens, mostly Claude Code's own startup context. That's about $0.29 at Opus 5.5 prices.

## Cleanup

The throwaway company "Spike Co (throwaway)" was deleted after this spike.
