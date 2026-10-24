// Real gateway client: REST + SSE (/events) + call WebSocket (/call/{role_id}).
import {
  CALL_EVENT_TYPES,
  SSE_EVENT_TYPES,
  type Board,
  type CallEvent,
  type CallSocket,
  type Gateway,
  type Role,
  type ServerEvent,
  type TaskDetail,
} from "./types";

export const BACKOFF_START_MS = 1000;
export const BACKOFF_MAX_MS = 10_000;

const WS_CONNECTING = 0;
const WS_OPEN = 1;

export class GatewayError extends Error {
  readonly status: number;
  readonly path: string;
  constructor(status: number, path: string) {
    super(`Gateway ${path} failed with HTTP ${status}`);
    this.name = "GatewayError";
    this.status = status;
    this.path = path;
  }
}

// The small slices of the browser APIs we use, so tests can pass fakes.
export interface EventSourceLike {
  addEventListener(type: string, listener: (e: { data?: unknown }) => void): void;
  close(): void;
}

export interface WebSocketLike {
  binaryType: string;
  readonly readyState: number;
  send(data: string | ArrayBuffer): void;
  close(code?: number, reason?: string): void;
  addEventListener(type: "message", listener: (e: { data?: unknown }) => void): void;
  addEventListener(type: "close", listener: (e: { code?: number }) => void): void;
}

export interface GatewayDeps {
  fetch?: (url: string) => Promise<Response>;
  eventSource?: (url: string) => EventSourceLike;
  webSocket?: (url: string) => WebSocketLike;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** Turns one SSE frame (`event: <type>`, `data: <json>`) into a ServerEvent, or null if it isn't one we know. */
export function parseSse(type: string, data: string): ServerEvent | null {
  if (!(SSE_EVENT_TYPES as readonly string[]).includes(type)) return null;
  const body = parseJson(data);
  if (!isRecord(body)) return null;
  return { ...body, type } as ServerEvent;
}

/** Turns one JSON text frame from the call socket into a CallEvent, or null if it isn't one we know. */
export function parseCallMessage(text: string): CallEvent | null {
  const body = parseJson(text);
  if (!isRecord(body) || typeof body.type !== "string") return null;
  if (!(CALL_EVENT_TYPES as readonly string[]).includes(body.type)) return null;
  return body as CallEvent;
}

export function createGateway(baseUrl: string, deps: GatewayDeps = {}): Gateway {
  const base = baseUrl.replace(/\/+$/, "");
  const wsBase = base.replace(/^http/, "ws"); // http -> ws, https -> wss
  const doFetch = deps.fetch ?? ((url: string) => fetch(url));
  const makeEventSource: (url: string) => EventSourceLike = deps.eventSource ?? ((url) => new EventSource(url));
  const makeWebSocket: (url: string) => WebSocketLike = deps.webSocket ?? ((url) => new WebSocket(url));

  async function getJson<T>(path: string): Promise<T> {
    const res = await doFetch(`${base}${path}`);
    if (!res.ok) throw new GatewayError(res.status, path);
    return (await res.json()) as T;
  }

  return {
    fetchRoles: () => getJson<Role[]>("/roles"),
    fetchBoard: () => getJson<Board>("/board"),
    fetchTask: (id) => getJson<TaskDetail>(`/tasks/${encodeURIComponent(id)}`),

    subscribe(onEvent) {
      let source: EventSourceLike | null = null;
      let timer: ReturnType<typeof setTimeout> | null = null;
      let delay = BACKOFF_START_MS;
      let reconnecting = false;
      let stopped = false;

      // We close on error and reconnect ourselves (instead of the browser's built-in retry)
      // so we control the backoff and know when to emit `resync`.
      const connect = () => {
        const es = makeEventSource(`${base}/events`);
        source = es;
        const live = () => !stopped && source === es;

        es.addEventListener("open", () => {
          if (!live()) return;
          delay = BACKOFF_START_MS;
          if (reconnecting) {
            reconnecting = false;
            onEvent({ type: "resync" });
          }
        });

        es.addEventListener("error", () => {
          if (!live()) return;
          es.close();
          source = null;
          reconnecting = true;
          timer = setTimeout(() => {
            timer = null;
            if (!stopped) connect();
          }, delay);
          delay = Math.min(delay * 2, BACKOFF_MAX_MS);
        });

        for (const type of SSE_EVENT_TYPES) {
          es.addEventListener(type, (msg) => {
            if (!live() || typeof msg.data !== "string") return;
            const event = parseSse(type, msg.data);
            if (event) onEvent(event);
          });
        }
      };

      connect();
      return () => {
        stopped = true;
        if (timer) clearTimeout(timer);
        source?.close();
        source = null;
      };
    },

    openCall(roleId): CallSocket {
      const ws = makeWebSocket(`${wsBase}/call/${encodeURIComponent(roleId)}`);
      ws.binaryType = "arraybuffer";
      const audioCbs: ((pcm: ArrayBuffer) => void)[] = [];
      const eventCbs: ((e: CallEvent) => void)[] = [];
      const closeCbs: ((code: number) => void)[] = [];

      ws.addEventListener("message", (msg) => {
        if (typeof msg.data === "string") {
          const event = parseCallMessage(msg.data);
          if (event) eventCbs.forEach((cb) => cb(event));
        } else if (msg.data instanceof ArrayBuffer) {
          const pcm = msg.data;
          audioCbs.forEach((cb) => cb(pcm));
        }
      });
      ws.addEventListener("close", (e) => {
        closeCbs.forEach((cb) => cb(e.code ?? 1005));
      });

      return {
        sendAudio(pcm) {
          if (ws.readyState === WS_OPEN) ws.send(pcm);
        },
        hangup() {
          if (ws.readyState === WS_OPEN) ws.send(JSON.stringify({ type: "hangup" }));
          if (ws.readyState === WS_OPEN || ws.readyState === WS_CONNECTING) ws.close(1000, "hangup");
        },
        onAudio: (cb) => void audioCbs.push(cb),
        onEvent: (cb) => void eventCbs.push(cb),
        onClose: (cb) => void closeCbs.push(cb),
      };
    },
  };
}
