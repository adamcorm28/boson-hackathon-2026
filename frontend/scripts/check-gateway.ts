// Contract check: drives the real frontend client + reducers against a running gateway, minus audio.
//   npm run check:gateway                               (gateway at http://localhost:8000)
//   GATEWAY_URL=http://localhost:8010 npm run check:gateway
// No Boson session is opened, so no credits are used.
//
// The live-events part needs a task created on a call (the watcher only reports those) and the
// mock company (it finishes the task with POST /dev/complete). Delegate something on a call first;
// otherwise that part is skipped.
import { BOARD_COLUMNS, type Board, type ServerEvent } from "../src/api/types";
import { createGateway, GatewayError } from "../src/api/gateway";
import { boardReducer } from "../src/board/boardReducer";
import { DESK_SPOTS, layoutDesks } from "../src/office/map";
import { initialOfficeState, officeReducer } from "../src/office/officeReducer";

const BASE = (process.env.GATEWAY_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const gw = createGateway(BASE);
let failures = 0;
const check = (ok: boolean, what: string, detail?: unknown) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${what}${!ok && detail !== undefined ? `  -> ${JSON.stringify(detail)}` : ""}`);
  if (!ok) failures++;
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const columnsOf = (b: Board, id: string) => BOARD_COLUMNS.filter((c) => b.columns[c].some((x) => x.task_id === id));

console.log(`Gateway: ${BASE}\n`);

// ---- REST ----

const roles = await gw.fetchRoles();
check(roles.length > 0, `GET /roles returns roles (${roles.length})`);
const desks = layoutDesks(roles);
const named = new Set(Object.values(DESK_SPOTS).map((s) => `${s.x},${s.y}`));
const autoPlaced = desks.filter((d) => !named.has(`${d.x},${d.y}`)).map((d) => d.roleId);
check(desks.length === roles.length, "every role gets a desk");
console.log(`      auto-placed (no known desk name): ${autoPlaced.join(", ") || "none"}`);

const board = await gw.fetchBoard();
check(BOARD_COLUMNS.every((c) => Array.isArray(board.columns[c])), "GET /board has all six columns");
const cards = BOARD_COLUMNS.flatMap((c) => board.columns[c]);
check(
  cards.length > 0 && cards.every((c) => c.task_id && c.title && c.status && (c.origin === "seed" || c.origin === "voice")),
  "cards have task_id / title / status / origin",
  cards[0],
);

const sample = cards[0];
const task = await gw.fetchTask(sample.task_id);
check(task.task_id === sample.task_id && Array.isArray(task.artifacts) && "result_summary" in task, `GET /tasks/${sample.task_id} shape`, task);
const notFound = await gw.fetchTask("NOPE-404").catch((e: unknown) => e);
check(notFound instanceof GatewayError && notFound.status === 404, "unknown task -> 404", String(notFound));

// ---- SSE: finish a call-created task and watch the events arrive ----

async function liveEvents() {
  const voiceTask = cards.find((c) => c.origin === "voice" && c.status !== "done");
  if (!voiceTask) {
    console.log("SKIP  live events: no unfinished task from a call on the board. Delegate something on a call, then re-run.");
    return;
  }
  const events: ServerEvent[] = [];
  const unsubscribe = gw.subscribe((e) => events.push(e));
  await sleep(500);

  const summary = "Checked by check-gateway.\nARTIFACT: link https://example.com/check Example link";
  const res = await fetch(`${BASE}/dev/complete/${encodeURIComponent(voiceTask.task_id)}?summary=${encodeURIComponent(summary)}`, {
    method: "POST",
  });
  if (res.status === 404) {
    unsubscribe();
    console.log("SKIP  live events: POST /dev/complete needs COMPANY_BACKEND=mock");
    return;
  }
  check(res.ok, `POST /dev/complete/${voiceTask.task_id}`, res.status);
  for (let i = 0; i < 40 && !events.some((e) => e.type === "ping"); i++) await sleep(250);
  unsubscribe();
  console.log("      events:", events.map((e) => e.type + ("status" in e ? `(${e.status})` : "")).join(", ") || "none");

  const completed = events.find((e) => e.type === "task.completed");
  check(completed?.type === "task.completed" && completed.task_id === voiceTask.task_id, "task.completed arrives and parses", completed);
  const ping = events.find((e) => e.type === "ping");
  check(ping?.type === "ping" && ping.task_id === voiceTask.task_id, "ping arrives and parses", ping);

  let office = initialOfficeState(roles);
  for (const e of events) office = officeReducer(office, e);
  const from = completed?.type === "task.completed" ? completed.from_role : "";
  check((office.bang[from] ?? []).includes(voiceTask.task_id), `"!" over ${from}`, office.bang);
  console.log("      toast:", office.toasts[0]?.text ?? "none");

  let local = board;
  for (const e of events) local = boardReducer(local, e);
  const fresh = await gw.fetchBoard();
  check(
    JSON.stringify(columnsOf(local, voiceTask.task_id)) === JSON.stringify(columnsOf(fresh, voiceTask.task_id)),
    "board after live updates matches a fresh GET /board",
    { local: columnsOf(local, voiceTask.task_id), server: columnsOf(fresh, voiceTask.task_id) },
  );

  const done = await gw.fetchTask(voiceTask.task_id);
  check(!!done.result_summary, "result_summary after completion", done);
  check(done.artifacts.length > 0 && done.artifacts.every((a) => /^https?:\/\//.test(a.url)), "artifacts parsed, URLs absolute", done.artifacts);
}
await liveEvents();

// ---- WS: rejection codes (no Boson session is started for these) ----

const code = await new Promise<number>((resolve) => {
  const call = gw.openCall("nobody_here");
  call.onClose(resolve);
  setTimeout(() => resolve(-1), 5000);
});
check(code === 4404, "WS /call/<unknown role> closes with 4404", code);

console.log(failures ? `\n${failures} FAILED` : "\nALL PASSED");
process.exit(failures ? 1 : 0);
