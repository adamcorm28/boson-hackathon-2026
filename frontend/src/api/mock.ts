// In-browser stand-in for the voice gateway (workstream A), behind the same Gateway interface.
//
// Script: call anyone. After their greeting, talk for ~2 s and they delegate "Fix bulk discount"
// to Dwight (task.started in the call, card appears on the board). 1.5 s later Dwight picks it up
// (in_progress); 10 s after the delegation it's done, with a diff, a task.completed and a ping.
// The ping goes to whoever you're on a call with (and they announce it), or to_role null if nobody.
// Loud mic audio while the agent talks triggers barge_in, like the real server VAD.
import { GatewayError } from "./gateway";
import {
  BOARD_COLUMNS,
  CLOSE_ALREADY_ON_CALL,
  type Artifact,
  type Board,
  type CallEvent,
  type CallSocket,
  type Card,
  type Gateway,
  type Role,
  type ServerEvent,
  type TaskDetail,
} from "./types";

export const MOCK_ROLES: Role[] = [
  { id: "ceo", name: "Michael Scott", title: "Regional Manager", reports_to: null, voice: "marcus", sprite: "michael", desk: "michael_office" },
  { id: "cfo", name: "Kevin Malone", title: "CFO (Accounting)", reports_to: "ceo", voice: "default", sprite: "kevin", desk: "accounting" },
  { id: "eng_lead", name: "Ryan Howard", title: "Engineering Lead (Dunder Mifflin Infinity)", reports_to: "ceo", voice: "default", sprite: "ryan", desk: "annex" },
  { id: "engineer", name: "Dwight Schrute", title: "Engineer", reports_to: "eng_lead", voice: "jake", sprite: "dwight", desk: "dwight_desk" },
  { id: "sales_lead", name: "Jim Halpert", title: "Sales Lead", reports_to: "ceo", voice: "oliver", sprite: "jim", desk: "jim_desk" },
];

const GREETINGS: Record<string, string> = {
  ceo: "Michael Scott, World's Best Boss. Talk to me.",
  cfo: "Hi. It's Kevin. I'm eating, but go ahead.",
  eng_lead: "Yeah, Ryan. Make it quick, I have a pitch.",
  engineer: "Dwight Schrute. State your business.",
  sales_lead: "Hey, it's Jim. What's up?",
};
const DEFAULT_GREETING = "Dunder Mifflin, this is a mock call. Go ahead.";

// Mirrors backend/company/data/issues_seed.json.
const SEED_CARDS: Omit<Card, "origin">[] = [
  { task_id: "DM-101", title: "Infinity checkout not applying bulk discount", status: "todo", assignee_role: "eng_lead" },
  { task_id: "DM-102", title: "Q4 numbers for David Wallace", status: "todo", assignee_role: "cfo" },
  { task_id: "DM-103", title: "Lackawanna County quote on hold", status: "blocked", assignee_role: "sales_lead" },
  { task_id: "DM-104", title: "September sales report", status: "done", assignee_role: "sales_lead" },
  { task_id: "DM-105", title: "Reconcile October expense reports", status: "in_progress", assignee_role: "cfo" },
  { task_id: "DM-106", title: "Plan the next fire drill", status: "backlog", assignee_role: "ceo" },
  { task_id: "DM-107", title: "Office party budget", status: "backlog", assignee_role: "cfo" },
  { task_id: "DM-108", title: "Renew Scranton Business Park account", status: "todo", assignee_role: "sales_lead" },
  { task_id: "DM-109", title: "Infinity layout broken on tablets", status: "backlog", assignee_role: "engineer" },
  { task_id: "DM-110", title: "Reply to Toby's HR reminder", status: "todo", assignee_role: "ceo" },
];

const FIX = { task_id: "DM-111", title: "Fix bulk discount", assignee_role: "engineer" } as const;
const FIX_SUMMARY =
  "Fixed the Infinity checkout: orders of 50 or more cases now get the 10% bulk discount. " +
  "Added two pricing tests; all tests pass.";
const SCRIPT = {
  userAsk: "Can you get Dwight to fix the bulk discount?",
  reply: "Done. I've asked Dwight to fix the bulk discount.",
  announce: "Quick update: Dwight just messaged. The bulk discount fix is done, and he wants it on record he did it single-handedly.",
};

// Unscaled timings in ms (divided by `speed`).
const T = { connect: 300, pickUp: 1500, work: 10_000, chunkInterval: 50 };

const BYTES_PER_SECOND = 24_000 * 2; // PCM16 mono 24 kHz
const TRIGGER_BYTES = 2 * BYTES_PER_SECOND; // ~2 s of mic audio after the greeting
const CHUNK_BYTES = BYTES_PER_SECOND / 10; // 100 ms frames, sent every 50 ms (2x real time, like a real server)
const BARGE_IN_RMS = 0.05; // normal speech on a real mic with auto-gain
const QUIET_BYTES = 0.6 * BYTES_PER_SECOND; // pause that counts as "done talking"

export interface MockOptions {
  /** Speeds up every timer, e.g. 10 = ten times faster. */
  speed?: number;
  /** Where public/mock/* is served. Defaults to the page origin. */
  assetBase?: string;
  /** Override the agent voice clip (PCM16 24 kHz mono). Defaults to fetching /mock/greeting.pcm. */
  loadAudio?: () => Promise<ArrayBuffer>;
}

export interface MockGateway extends Gateway {
  /** Ends the active call from the "server" side, like an idle timeout: call.ended, then close. */
  endActiveCall(reason: string): void;
  /** Plays your side of the scripted call without a mic: the hand-off to Dwight. */
  simulateUserTurn(): void;
  /** Pretends the SSE stream dropped and came back. */
  resync(): void;
}

interface ActiveCall {
  roleId: string;
  announce(text: string): void;
  end(reason: string): void;
  /** The scripted user turn ("Can you get Dwight to fix the bulk discount?"). */
  userTurn(): void;
}

export function createMockGateway(opts: MockOptions = {}): MockGateway {
  const speed = opts.speed ?? 1;
  const assetBase = opts.assetBase ?? (typeof location !== "undefined" ? location.origin : "http://localhost:5173");
  const later = (ms: number, fn: () => void) => setTimeout(fn, ms / speed);

  const board: Board = { columns: Object.fromEntries(BOARD_COLUMNS.map((c) => [c, []])) as unknown as Board["columns"] };
  for (const card of SEED_CARDS) board.columns[card.status as keyof Board["columns"]].push({ ...card, origin: "seed" });
  const results = new Map<string, { summary: string; artifacts: Artifact[] }>();
  const listeners = new Set<(e: ServerEvent) => void>();
  let active: ActiveCall | null = null;
  let delegated = false;

  let audioClip: Promise<ArrayBuffer> | null = null;
  const loadClip = () =>
    (audioClip ??= (opts.loadAudio ?? (() => fetchClip(`${assetBase}/mock/greeting.pcm`)))().catch((err) => {
      console.warn("mock gateway: couldn't load greeting.pcm, using a tone instead", err);
      return tone(1);
    }));

  function findCard(taskId: string): Card | undefined {
    for (const col of BOARD_COLUMNS) {
      const card = board.columns[col].find((c) => c.task_id === taskId);
      if (card) return card;
    }
    return undefined;
  }

  function broadcast(e: ServerEvent) {
    if (e.type === "task.updated") {
      const prev = findCard(e.task_id);
      for (const col of BOARD_COLUMNS) board.columns[col] = board.columns[col].filter((c) => c.task_id !== e.task_id);
      if (e.status !== "cancelled") {
        board.columns[e.status].push({
          task_id: e.task_id,
          title: e.title,
          assignee_role: e.assignee_role,
          status: e.status,
          origin: prev?.origin ?? "voice",
        });
      }
    }
    for (const l of [...listeners]) l(e);
  }

  function delegateFix() {
    delegated = true;
    broadcast({ type: "task.updated", ...FIX, status: "todo" });
    later(T.pickUp, () => {
      broadcast({ type: "task.updated", ...FIX, status: "in_progress" });
      broadcast({ type: "agent.status", role: FIX.assignee_role, state: "working" });
    });
    later(T.work, () => {
      results.set(FIX.task_id, {
        summary: FIX_SUMMARY,
        artifacts: [{ kind: "diff", url: `${assetBase}/mock/fix.diff`, label: "Bulk discount fix (checkout/pricing.js)" }],
      });
      broadcast({ type: "task.updated", ...FIX, status: "done" });
      broadcast({ type: "agent.status", role: FIX.assignee_role, state: "idle" });
      broadcast({ type: "task.completed", task_id: FIX.task_id, from_role: FIX.assignee_role, title: FIX.title, summary: FIX_SUMMARY });
      const call = active;
      broadcast({ type: "ping", to_role: call?.roleId ?? null, from_role: FIX.assignee_role, task_id: FIX.task_id, text: FIX_SUMMARY });
      call?.announce(SCRIPT.announce);
    });
  }

  function openCall(roleId: string): CallSocket {
    const audioCbs: ((pcm: ArrayBuffer) => void)[] = [];
    const eventCbs: ((e: CallEvent) => void)[] = [];
    const closeCbs: ((code: number) => void)[] = [];
    const timers = new Set<ReturnType<typeof setTimeout>>();
    let open = false;
    let closed = false;
    let speechId = 0; // bumping it cancels the speech in flight
    let speaking = false;
    let listening = false; // true once the greeting has finished or been interrupted
    let heard = 0;
    let quiet = 0; // bytes of quiet mic audio in a row

    const callLater = (ms: number, fn: () => void) => {
      const id = later(ms, () => {
        timers.delete(id);
        fn();
      });
      timers.add(id);
    };
    const send = (e: CallEvent) => {
      if (open) eventCbs.forEach((cb) => cb(e));
    };
    const close = (code: number) => {
      if (closed) return;
      closed = true;
      open = false;
      speechId++;
      timers.forEach(clearTimeout);
      timers.clear();
      if (active === call) {
        active = null;
        broadcast({ type: "agent.status", role: roleId, state: "idle" });
      }
      setTimeout(() => closeCbs.forEach((cb) => cb(code)), 0); // async, like a real socket
    };

    const stopSpeaking = () => {
      speechId++;
      if (speaking) {
        speaking = false;
        send({ type: "agent.speaking", value: false });
      }
    };

    const speak = (text: string, onDone?: () => void) => {
      stopSpeaking();
      const id = speechId;
      void loadClip().then((pcm) => {
        if (id !== speechId || !open) return;
        const chunks = splitBuffer(pcm, CHUNK_BYTES);
        const words = text.split(" ");
        let i = 0;
        speaking = true;
        send({ type: "agent.speaking", value: true });
        const tick = () => {
          if (id !== speechId || !open) return;
          const from = Math.floor((i * words.length) / chunks.length);
          const to = Math.floor(((i + 1) * words.length) / chunks.length);
          if (to > from) send({ type: "transcript.assistant.delta", text: (from > 0 ? " " : "") + words.slice(from, to).join(" ") });
          const chunk = chunks[i];
          audioCbs.forEach((cb) => cb(chunk));
          i++;
          if (i < chunks.length) {
            callLater(T.chunkInterval, tick);
          } else {
            speaking = false;
            send({ type: "transcript.assistant.done", text });
            send({ type: "agent.speaking", value: false });
            onDone?.();
          }
        };
        tick();
      });
    };

    const respondToUser = () => {
      if (!open || delegated) return;
      send({ type: "transcript.user", text: SCRIPT.userAsk });
      send({
        type: "tool.called",
        name: "delegate_task",
        args: { assignee_role: FIX.assignee_role, title: FIX.title, brief: "Bulk discount isn't applied at checkout." },
      });
      send({ type: "task.started", ...FIX });
      delegateFix();
      speak(SCRIPT.reply);
    };

    const call: ActiveCall = {
      roleId,
      userTurn: respondToUser,
      announce: (text) => speak(text),
      end: (reason) => {
        send({ type: "call.ended", reason });
        close(1000);
      },
    };

    if (active) {
      // Same as the real gateway: only one call at a time.
      setTimeout(() => closeCbs.forEach((cb) => cb(CLOSE_ALREADY_ON_CALL)), T.connect / speed);
      closed = true;
    } else {
      active = call;
      callLater(T.connect, () => {
        open = true;
        send({ type: "call.started", role: roleId });
        broadcast({ type: "agent.status", role: roleId, state: "on_call" });
        speak(GREETINGS[roleId] ?? DEFAULT_GREETING, () => {
          listening = true;
        });
      });
    }

    return {
      sendAudio(pcm) {
        if (!open) return;
        const loud = rms(pcm) > BARGE_IN_RMS;
        if (speaking && loud) {
          // Real order: speech_started -> barge_in, then the cancelled response ends -> speaking false.
          send({ type: "barge_in" });
          stopSpeaking();
          listening = true;
          return;
        }
        if (!listening || delegated) return;
        heard += pcm.byteLength;
        quiet = loud ? 0 : quiet + pcm.byteLength;
        // Like server VAD: reply once they've talked ~2 s and then paused.
        if (heard < TRIGGER_BYTES || quiet < QUIET_BYTES) return;
        respondToUser();
      },
      hangup: () => close(1000),
      onAudio: (cb) => void audioCbs.push(cb),
      onEvent: (cb) => void eventCbs.push(cb),
      onClose: (cb) => void closeCbs.push(cb),
    };
  }

  return {
    fetchRoles: async () => structuredClone(MOCK_ROLES),
    fetchBoard: async () => structuredClone(board),
    async fetchTask(id) {
      const card = findCard(id);
      if (!card) throw new GatewayError(404, `/tasks/${id}`);
      const result = results.get(id);
      const detail: TaskDetail = {
        task_id: card.task_id,
        title: card.title,
        assignee_role: card.assignee_role,
        status: card.status,
        result_summary: result?.summary ?? null,
        artifacts: result?.artifacts ?? [],
      };
      return structuredClone(detail);
    },
    subscribe(onEvent) {
      listeners.add(onEvent);
      return () => void listeners.delete(onEvent);
    },
    openCall,
    endActiveCall: (reason) => active?.end(reason),
    simulateUserTurn: () => active?.userTurn(),
    resync: () => broadcast({ type: "resync" }),
  };
}

// ---- helpers ----

async function fetchClip(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.arrayBuffer();
}

function splitBuffer(buf: ArrayBuffer, size: number): ArrayBuffer[] {
  const out: ArrayBuffer[] = [];
  for (let start = 0; start < buf.byteLength; start += size) out.push(buf.slice(start, start + size));
  return out.length ? out : [new ArrayBuffer(0)];
}

/** Root-mean-square level of a PCM16 frame, 0..1. */
function rms(pcm: ArrayBuffer): number {
  const samples = new Int16Array(pcm, 0, Math.floor(pcm.byteLength / 2));
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const s of samples) sum += s * s;
  return Math.sqrt(sum / samples.length) / 32768;
}

/** A soft 440 Hz tone, used if greeting.pcm can't be fetched. */
function tone(seconds: number): ArrayBuffer {
  const samples = new Int16Array(Math.round(24_000 * seconds));
  for (let i = 0; i < samples.length; i++) samples[i] = Math.round(0.2 * 32767 * Math.sin((2 * Math.PI * 440 * i) / 24_000));
  return samples.buffer;
}
