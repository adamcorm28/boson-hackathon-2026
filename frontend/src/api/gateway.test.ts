import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createGateway, GatewayError, parseCallMessage, parseSse } from "./gateway";
import type { CallEvent, ServerEvent } from "./types";

// ---- fakes ----

type Listener = (e: { data?: unknown; code?: number }) => void;

class FakeEventSource {
  closed = false;
  private listeners = new Map<string, Listener[]>();
  constructor(readonly url: string) {}
  addEventListener(type: string, fn: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close() {
    this.closed = true;
  }
  fire(type: string, data?: string) {
    for (const fn of this.listeners.get(type) ?? []) fn({ data });
  }
}

class FakeWebSocket {
  binaryType = "blob";
  readyState = 0; // CONNECTING
  sent: (string | ArrayBuffer)[] = [];
  closedWith: number | undefined;
  private listeners = new Map<string, Listener[]>();
  constructor(readonly url: string) {}
  addEventListener(type: string, fn: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }
  close(code?: number) {
    this.closedWith = code;
    this.readyState = 3;
  }
  // test helpers
  open() {
    this.readyState = 1;
    this.fire("open", {});
  }
  fire(type: string, e: { data?: unknown; code?: number }) {
    for (const fn of this.listeners.get(type) ?? []) fn(e);
  }
}

function setup() {
  const sources: FakeEventSource[] = [];
  const sockets: FakeWebSocket[] = [];
  const fetch = vi.fn<(url: string) => Promise<Response>>();
  const gw = createGateway("http://localhost:8000/", {
    fetch,
    eventSource: (url) => {
      const s = new FakeEventSource(url);
      sources.push(s);
      return s;
    },
    webSocket: (url) => {
      const s = new FakeWebSocket(url);
      sockets.push(s);
      return s;
    },
  });
  return { gw, sources, sockets, fetch };
}

// ---- parsing ----

describe("parseSse", () => {
  it("parses SSE ping event into ServerEvent", () => {
    const data = JSON.stringify({ to_role: null, from_role: "engineer", task_id: "DM-101", text: "Fix is done" });
    expect(parseSse("ping", data)).toEqual({
      type: "ping",
      to_role: null,
      from_role: "engineer",
      task_id: "DM-101",
      text: "Fix is done",
    });
  });

  it("returns null for unknown event types and malformed data", () => {
    expect(parseSse("mystery", "{}")).toBeNull();
    expect(parseSse("ping", "not json")).toBeNull();
    expect(parseSse("ping", "[1,2]")).toBeNull();
  });
});

describe("parseCallMessage", () => {
  it("parses known call events and ignores unknown ones", () => {
    expect(parseCallMessage('{"type":"agent.speaking","value":true}')).toEqual({ type: "agent.speaking", value: true });
    expect(parseCallMessage('{"type":"barge_in"}')).toEqual({ type: "barge_in" });
    expect(parseCallMessage('{"type":"nope"}')).toBeNull();
    expect(parseCallMessage('{"value":1}')).toBeNull();
    expect(parseCallMessage("garbage")).toBeNull();
  });
});

// ---- SSE subscription ----

describe("subscribe", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("delivers named SSE events from /events", () => {
    const { gw, sources } = setup();
    const seen: ServerEvent[] = [];
    gw.subscribe((e) => seen.push(e));

    expect(sources[0].url).toBe("http://localhost:8000/events");
    sources[0].fire("open");
    sources[0].fire("task.updated", JSON.stringify({ task_id: "DM-101", status: "in_progress", assignee_role: "engineer", title: "Fix" }));
    sources[0].fire("agent.status", "garbage");

    expect(seen).toEqual([
      { type: "task.updated", task_id: "DM-101", status: "in_progress", assignee_role: "engineer", title: "Fix" },
    ]);
  });

  it("resync emitted after reconnect", () => {
    const { gw, sources } = setup();
    const seen: ServerEvent[] = [];
    gw.subscribe((e) => seen.push(e));

    sources[0].fire("open");
    expect(seen).toEqual([]); // no resync on the first connect

    sources[0].fire("error");
    expect(sources[0].closed).toBe(true);
    expect(sources).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(sources).toHaveLength(2);
    sources[1].fire("open");
    expect(seen).toEqual([{ type: "resync" }]);
  });

  it("reconnect backoff is 1, 2, 4, 8 s then capped at 10 s", () => {
    const { gw, sources } = setup();
    gw.subscribe(() => {});

    const waits = [1000, 2000, 4000, 8000, 10000, 10000];
    waits.forEach((ms, i) => {
      sources[i].fire("error");
      vi.advanceTimersByTime(ms - 1);
      expect(sources).toHaveLength(i + 1);
      vi.advanceTimersByTime(1);
      expect(sources).toHaveLength(i + 2);
    });
  });

  it("backoff resets after a successful reconnect", () => {
    const { gw, sources } = setup();
    gw.subscribe(() => {});

    sources[0].fire("error");
    vi.advanceTimersByTime(1000);
    sources[1].fire("error");
    vi.advanceTimersByTime(2000);
    sources[2].fire("open"); // healthy again
    sources[2].fire("error");
    vi.advanceTimersByTime(1000);
    expect(sources).toHaveLength(4);
  });

  it("unsubscribe closes the stream and cancels a pending reconnect", () => {
    const { gw, sources } = setup();
    const seen: ServerEvent[] = [];
    const unsubscribe = gw.subscribe((e) => seen.push(e));

    sources[0].fire("error");
    unsubscribe();
    vi.advanceTimersByTime(60_000);
    expect(sources).toHaveLength(1);

    const second = setup();
    const stop = second.gw.subscribe((e) => seen.push(e));
    stop();
    expect(second.sources[0].closed).toBe(true);
    second.sources[0].fire("ping", JSON.stringify({ to_role: null, from_role: "x", task_id: "t", text: "" }));
    expect(seen).toEqual([]);
  });
});

// ---- REST ----

describe("REST", () => {
  it("fetchRoles GETs /roles", async () => {
    const { gw, fetch } = setup();
    const roles = [{ id: "ceo", name: "Michael Scott", title: "Regional Manager", reports_to: null, voice: "marcus" }];
    fetch.mockResolvedValue(new Response(JSON.stringify(roles), { status: 200 }));

    await expect(gw.fetchRoles()).resolves.toEqual(roles);
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/roles");
  });

  it("fetchTask encodes the id and throws GatewayError on HTTP errors", async () => {
    const { gw, fetch } = setup();
    fetch.mockResolvedValue(new Response("not found", { status: 404 }));

    const err = await gw.fetchTask("DM 1/2").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GatewayError);
    expect((err as GatewayError).status).toBe(404);
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/tasks/DM%201%2F2");
  });
});

// ---- WS call ----

describe("openCall", () => {
  it("connects to ws://.../call/{role} with binary frames as ArrayBuffer", () => {
    const { gw, sockets } = setup();
    gw.openCall("sales_lead");
    expect(sockets[0].url).toBe("ws://localhost:8000/call/sales_lead");
    expect(sockets[0].binaryType).toBe("arraybuffer");
  });

  it("routes binary frames to onAudio and JSON frames to onEvent", () => {
    const { gw, sockets } = setup();
    const call = gw.openCall("ceo");
    const audio: ArrayBuffer[] = [];
    const events: CallEvent[] = [];
    call.onAudio((pcm) => audio.push(pcm));
    call.onEvent((e) => events.push(e));

    const chunk = new ArrayBuffer(960);
    sockets[0].open();
    sockets[0].fire("message", { data: '{"type":"call.started","role":"ceo"}' });
    sockets[0].fire("message", { data: chunk });
    sockets[0].fire("message", { data: '{"type":"unknown.thing"}' });

    expect(events).toEqual([{ type: "call.started", role: "ceo" }]);
    expect(audio).toEqual([chunk]);
  });

  it("sendAudio only sends once open", () => {
    const { gw, sockets } = setup();
    const call = gw.openCall("ceo");
    call.sendAudio(new ArrayBuffer(4)); // still connecting: dropped
    sockets[0].open();
    const frame = new ArrayBuffer(8);
    call.sendAudio(frame);
    expect(sockets[0].sent).toEqual([frame]);
  });

  it("hangup sends the hangup message and closes", () => {
    const { gw, sockets } = setup();
    const call = gw.openCall("ceo");
    sockets[0].open();
    call.hangup();
    expect(sockets[0].sent).toEqual(['{"type":"hangup"}']);
    expect(sockets[0].closedWith).toBe(1000);
  });

  it("onClose reports the close code (4409 = already on a call)", () => {
    const { gw, sockets } = setup();
    const call = gw.openCall("ceo");
    const codes: number[] = [];
    call.onClose((code) => codes.push(code));
    sockets[0].fire("close", { code: 4409 });
    expect(codes).toEqual([4409]);
  });
});
