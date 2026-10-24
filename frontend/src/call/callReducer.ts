// Call window state. Pure: actions are the gateway's CallEvents plus a few local ones.
import { CLOSE_ALREADY_ON_CALL, CLOSE_UNKNOWN_ROLE, type CallEvent } from "../api/types";

export const ALREADY_ON_CALL_TEXT = "Already on a call";
export const UNKNOWN_ROLE_TEXT = "Nobody by that name works here";
export const MIC_BLOCKED_TEXT = "Mic blocked — allow microphone and retry";

export interface CallLine {
  speaker: "user" | "agent";
  text: string;
  final: boolean;
}

export interface CallTask {
  task_id: string;
  title: string;
  assignee_role: string;
}

export interface CallState {
  status: "idle" | "connecting" | "live" | "ended";
  roleId: string | null;
  speaking: boolean;
  lines: CallLine[];
  tasks: CallTask[];
  /** Call-level problem (already on a call, connection lost). */
  error: string | null;
  /** Mic problem; the call stays up so you can still hear them. */
  micError: string | null;
  endReason: string | null;
  /** Why the live avatar video isn't showing, if it failed to start. */
  videoNotice: string | null;
}

export type CallAction =
  | CallEvent
  | { type: "dial"; roleId: string }
  | { type: "closed"; code: number }
  | { type: "mic_blocked"; message?: string }
  | { type: "mic_ok" }
  | { type: "dismiss" };

export const initialCallState: CallState = {
  status: "idle",
  roleId: null,
  speaking: false,
  lines: [],
  tasks: [],
  error: null,
  micError: null,
  endReason: null,
  videoNotice: null,
};

const openAgentLine = (lines: CallLine[]) => lines.findLastIndex((l) => l.speaker === "agent" && !l.final);

function finalizeOpen(lines: CallLine[]): CallLine[] {
  const i = openAgentLine(lines);
  return i < 0 ? lines : lines.map((l, j) => (j === i ? { ...l, final: true } : l));
}

export function callReducer(state: CallState, action: CallAction): CallState {
  switch (action.type) {
    case "dial":
      return { ...initialCallState, status: "connecting", roleId: action.roleId };
    case "dismiss":
      return initialCallState;
  }

  // Everything below belongs to an open call.
  if (state.status === "idle" || state.status === "ended") return state;

  switch (action.type) {
    case "call.started":
      return { ...state, status: "live" };

    case "transcript.user": {
      const line: CallLine = { speaker: "user", text: action.text, final: true };
      // User transcripts often arrive after the reply has started; keep them in spoken order.
      const i = openAgentLine(state.lines);
      const lines = i < 0 ? [...state.lines, line] : [...state.lines.slice(0, i), line, ...state.lines.slice(i)];
      return { ...state, lines };
    }

    case "transcript.assistant.delta": {
      const i = openAgentLine(state.lines);
      const lines =
        i < 0
          ? [...state.lines, { speaker: "agent" as const, text: action.text, final: false }]
          : state.lines.map((l, j) => (j === i ? { ...l, text: l.text + action.text } : l));
      return { ...state, lines };
    }

    case "transcript.assistant.done": {
      const i = openAgentLine(state.lines);
      const lines =
        i < 0
          ? [...state.lines, { speaker: "agent" as const, text: action.text, final: true }]
          : state.lines.map((l, j) => (j === i ? { ...l, text: action.text, final: true } : l));
      return { ...state, lines };
    }

    case "barge_in":
      return { ...state, speaking: false, lines: finalizeOpen(state.lines) };

    case "agent.speaking":
      return state.speaking === action.value ? state : { ...state, speaking: action.value };

    case "task.started":
      if (state.tasks.some((t) => t.task_id === action.task_id)) return state;
      return {
        ...state,
        tasks: [...state.tasks, { task_id: action.task_id, title: action.title, assignee_role: action.assignee_role }],
      };

    case "call.ended":
      return { ...state, status: "ended", speaking: false, endReason: action.reason, lines: finalizeOpen(state.lines) };

    case "closed": {
      let error = state.error;
      if (action.code === CLOSE_ALREADY_ON_CALL) error = ALREADY_ON_CALL_TEXT;
      else if (action.code === CLOSE_UNKNOWN_ROLE) error = UNKNOWN_ROLE_TEXT;
      else if (action.code === 1006) error = state.status === "connecting" ? "Can't reach the gateway" : "Lost connection to the gateway";
      return { ...state, status: "ended", speaking: false, error, lines: finalizeOpen(state.lines) };
    }

    case "mic_blocked":
      return { ...state, micError: action.message ?? MIC_BLOCKED_TEXT };

    case "mic_ok":
      return state.micError === null ? state : { ...state, micError: null };

    case "avatar.unavailable":
      return {
        ...state,
        videoNotice: action.reason === "busy" ? "Video unavailable: Boson's avatars are all busy" : "Video unavailable",
      };

    default:
      return state; // tool.called and anything unknown
  }
}
