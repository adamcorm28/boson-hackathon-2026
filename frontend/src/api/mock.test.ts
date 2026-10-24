import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GatewayError } from "./gateway";
import { createMockGateway, MOCK_ROLES } from "./mock";
import type { CallEvent, ServerEvent } from "./types";

// 10x faster. Fake timers make tests instant anyway; this keeps every delay a whole ms
// (vitest's fake clock truncates fractional delays, which would scramble the order).
const SPEED = 10;
const GREETING_MS = 100; // connect + 0.3 s greeting
const SCRIPT_MS = 1500; // pick-up + 10 s of work + announcement
const ASSETS = "http://localhost:5173";
const clip = (seconds: number) => new ArrayBuffer(Math.round(seconds * 24000) * 2);
const silence40ms = () => new ArrayBuffer(1920); // 40 ms of PCM16 24 kHz
const loud40ms = () => new Int16Array(960).fill(12000).buffer;

function setup() {
  const gw = createMockGateway({ speed: SPEED, assetBase: ASSETS, loadAudio: async () => clip(0.3) });
  const log: string[] = [];
  const sse: ServerEvent[] = [];
  const callEvents: CallEvent[] = [];
  gw.subscribe((e) => {
    sse.push(e);
    if (e.type === "task.updated") log.push(`sse:task.updated(${e.task_id}:${e.status})`);
    else if (e.type === "agent.status") log.push(`sse:agent.status(${e.role}:${e.state})`);
    else log.push(`sse:${e.type}`);
  });
  return { gw, log, sse, callEvents };
}

function dial(ctx: ReturnType<typeof setup>, roleId: string) {
  const call = ctx.gw.openCall(roleId);
  const audio: ArrayBuffer[] = [];
  const closes: number[] = [];
  call.onEvent((e) => {
    ctx.callEvents.push(e);
    if (e.type !== "transcript.assistant.delta" && e.type !== "agent.speaking") ctx.log.push(`call:${e.type}`);
  });
  call.onAudio((pcm) => audio.push(pcm));
  call.onClose((code) => closes.push(code));
  return { call, audio, closes };
}

/** ~2 s of quiet mic audio, which triggers the scripted delegation once the greeting is over. */
function talk(call: { sendAudio(pcm: ArrayBuffer): void }) {
  for (let i = 0; i < 50; i++) call.sendAudio(silence40ms());
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("mock gateway", () => {
  it("serves five roles and a seeded board with the bulk-discount card in todo", async () => {
    const { gw } = setup();
    const roles = await gw.fetchRoles();
    expect(roles.map((r) => [r.id, r.desk])).toEqual([
      ["ceo", "michael_office"],
      ["cfo", "accounting"],
      ["eng_lead", "annex"],
      ["engineer", "dwight_desk"],
      ["sales_lead", "jim_desk"],
    ]);
    const board = await gw.fetchBoard();
    expect(board.columns.todo.map((c) => c.task_id)).toContain("DM-101");
    expect(Object.keys(board.columns).sort()).toEqual(
      ["backlog", "blocked", "done", "in_progress", "in_review", "todo"],
    );
  });

  it("mock scripted sequence", async () => {
    const ctx = setup();
    const { call, audio } = dial(ctx, "eng_lead");

    await vi.advanceTimersByTimeAsync(GREETING_MS);
    expect(audio.length).toBeGreaterThan(0);
    talk(call);
    await vi.advanceTimersByTimeAsync(SCRIPT_MS);

    expect(ctx.log).toEqual([
      "call:call.started",
      "sse:agent.status(eng_lead:on_call)",
      "call:transcript.assistant.done", // greeting
      "call:transcript.user",
      "call:tool.called",
      "call:task.started",
      "sse:task.updated(DM-111:todo)",
      "call:transcript.assistant.done", // "Dwight is on it"
      "sse:task.updated(DM-111:in_progress)",
      "sse:agent.status(engineer:working)",
      "sse:task.updated(DM-111:done)",
      "sse:agent.status(engineer:idle)",
      "sse:task.completed",
      "sse:ping",
      "call:transcript.assistant.done", // the announcement inside the call
    ]);
  });

  it("streams greeting audio wrapped in agent.speaking true/false, with deltas that add up to the done text", async () => {
    const ctx = setup();
    const { audio } = dial(ctx, "ceo");
    await vi.advanceTimersByTimeAsync(GREETING_MS);

    const types = ctx.callEvents.map((e) => e.type);
    expect(types[0]).toBe("call.started");
    expect(types[1]).toBe("agent.speaking");
    expect(types.at(-1)).toBe("agent.speaking");
    expect(ctx.callEvents.filter((e) => e.type === "agent.speaking")).toEqual([
      { type: "agent.speaking", value: true },
      { type: "agent.speaking", value: false },
    ]);

    const deltas = ctx.callEvents.flatMap((e) => (e.type === "transcript.assistant.delta" ? [e.text] : []));
    const done = ctx.callEvents.find((e) => e.type === "transcript.assistant.done");
    expect(done?.type === "transcript.assistant.done" && deltas.join("")).toBe(
      done?.type === "transcript.assistant.done" ? done.text : null,
    );
    expect(audio).toHaveLength(3); // 0.3 s clip in 100 ms frames
    expect(audio.reduce((n, a) => n + a.byteLength, 0)).toBe(clip(0.3).byteLength);
  });

  it("pings the active call's role, and announces it in the call", async () => {
    const ctx = setup();
    const { call } = dial(ctx, "sales_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    talk(call);
    await vi.advanceTimersByTimeAsync(SCRIPT_MS);

    const ping = ctx.sse.find((e) => e.type === "ping");
    expect(ping).toMatchObject({ type: "ping", to_role: "sales_lead", from_role: "engineer", task_id: "DM-111" });
    const completed = ctx.sse.find((e) => e.type === "task.completed");
    expect(completed).toMatchObject({ from_role: "engineer", title: "Fix bulk discount" });
  });

  it("pings with to_role null when nobody is on a call", async () => {
    const ctx = setup();
    const { call, closes } = dial(ctx, "eng_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    talk(call);
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    call.hangup();
    await vi.advanceTimersByTimeAsync(SCRIPT_MS);

    expect(closes).toEqual([1000]);
    expect(ctx.log).toContain("sse:agent.status(eng_lead:idle)");
    expect(ctx.sse.find((e) => e.type === "ping")).toMatchObject({ to_role: null, from_role: "engineer" });
  });

  it("delegates only once per mock session", async () => {
    const ctx = setup();
    const first = dial(ctx, "eng_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    talk(first.call);
    first.call.hangup();
    await vi.advanceTimersByTimeAsync(10);
    const second = dial(ctx, "eng_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    talk(second.call);
    await vi.advanceTimersByTimeAsync(SCRIPT_MS);
    expect(ctx.log.filter((l) => l === "call:task.started")).toHaveLength(1);
  });

  it("closes a second concurrent call with 4409", async () => {
    const ctx = setup();
    dial(ctx, "ceo");
    const second = dial(ctx, "sales_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    expect(second.closes).toEqual([4409]);
    expect(ctx.log.filter((l) => l === "call:call.started")).toHaveLength(1);
  });

  it("loud mic audio while the agent is speaking triggers barge_in and stops the audio", async () => {
    const gw = createMockGateway({ speed: 1, assetBase: ASSETS, loadAudio: async () => clip(3) });
    const events: CallEvent[] = [];
    const audio: ArrayBuffer[] = [];
    const call = gw.openCall("engineer");
    call.onEvent((e) => events.push(e));
    call.onAudio((pcm) => audio.push(pcm));

    await vi.advanceTimersByTimeAsync(500); // connected, greeting partly streamed
    const framesBefore = audio.length;
    expect(framesBefore).toBeGreaterThan(0);
    expect(framesBefore).toBeLessThan(30);

    call.sendAudio(loud40ms());
    await vi.advanceTimersByTimeAsync(5000);

    expect(audio.length).toBe(framesBefore);
    expect(events.map((e) => e.type)).toContain("barge_in");
    expect(events.at(-1)).toEqual({ type: "agent.speaking", value: false });
  });

  it("endActiveCall ends the call from the server side", async () => {
    const ctx = setup();
    const { closes } = dial(ctx, "cfo");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    ctx.gw.endActiveCall("idle_timeout");
    await vi.advanceTimersByTimeAsync(10);

    expect(ctx.callEvents.at(-1)).toEqual({ type: "call.ended", reason: "idle_timeout" });
    expect(closes).toEqual([1000]);
    expect(ctx.log.at(-1)).toBe("sse:agent.status(cfo:idle)");
  });

  it("board and task detail reflect the finished fix", async () => {
    const ctx = setup();
    const { call } = dial(ctx, "eng_lead");
    await vi.advanceTimersByTimeAsync(GREETING_MS);
    talk(call);
    await vi.advanceTimersByTimeAsync(SCRIPT_MS);

    const board = await ctx.gw.fetchBoard();
    const columnsWithFix = Object.entries(board.columns).filter(([, cards]) =>
      cards.some((c) => c.task_id === "DM-111"),
    );
    expect(columnsWithFix.map(([col]) => col)).toEqual(["done"]);

    const task = await ctx.gw.fetchTask("DM-111");
    expect(task.status).toBe("done");
    expect(task.result_summary).toMatch(/bulk discount/i);
    expect(task.artifacts).toEqual([
      { kind: "diff", url: `${ASSETS}/mock/fix.diff`, label: expect.any(String) },
    ]);

    const untouched = await ctx.gw.fetchTask("DM-102");
    expect(untouched.result_summary).toBeNull();
  });

  it("fetchTask rejects unknown ids with a 404 GatewayError", async () => {
    const { gw } = setup();
    const err = await gw.fetchTask("DM-999").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GatewayError);
    expect((err as GatewayError).status).toBe(404);
  });

  it("returns copies, so callers can't mutate the mock's state", async () => {
    const { gw } = setup();
    const roles = await gw.fetchRoles();
    roles[0].name = "Todd Packer";
    expect((await gw.fetchRoles())[0].name).toBe(MOCK_ROLES[0].name);
  });

  it("resync() emits a resync event", () => {
    const ctx = setup();
    ctx.gw.resync();
    expect(ctx.sse).toEqual([{ type: "resync" }]);
  });
});
