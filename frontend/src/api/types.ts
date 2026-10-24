// TypeScript mirror of the gateway <-> frontend contract.
// Source of truth: spec §7a + "Shared contract 2" in docs/superpowers/plans/2026-10-23-voice-company-index.md.
// Change a shape here only after agreeing it with the gateway owner (workstream A).

export type Status =
  | "backlog"
  | "todo"
  | "in_progress"
  | "in_review"
  | "blocked"
  | "done"
  | "cancelled";

/** The six whiteboard columns. `cancelled` is not a column: agreed with A, cancelled cards are dropped. */
export type BoardColumn = Exclude<Status, "cancelled">;
export const BOARD_COLUMNS: readonly BoardColumn[] = [
  "backlog",
  "todo",
  "in_progress",
  "in_review",
  "blocked",
  "done",
];

// ---- REST ----

/** GET /roles */
export interface Role {
  id: string;
  name: string; // full character name, e.g. "Dwight Schrute"
  title: string;
  reports_to: string | null;
  voice: string;
  sprite?: string | null;
  desk?: string | null; // named spot, e.g. "jim_desk"; missing/unknown = auto-placed
  /** What they're responsible for, shown on the contact profile (optional). */
  responsibilities?: string[];
  /** Still face from backend/data/avatars/; when set, the call shows it instead of the pixel portrait. */
  avatar_url?: string | null;
  /** Muted talking clip of that face, looped while the agent speaks (null in the gateway's sync mode). */
  avatar_loop_url?: string | null;
  /** Muted listening loop of that face (blinks, small moves), played whenever it isn't talking. */
  avatar_idle_url?: string | null;
  /** Boson live avatar: the call sends `avatar.room` and the voice plays from that room, lip-synced. */
  avatar_live?: boolean;
}

export interface Card {
  task_id: string;
  title: string;
  assignee_role: string | null;
  status: Status;
  origin: "voice" | "seed";
}

/** GET /roles/{role_id}/status: what someone is doing right now. */
export interface AgentStatusDetail {
  role: string;
  state: "idle" | "working";
  current_task_id: string | null;
  /** The latest note on their current task, e.g. a progress update. */
  last_comment: string | null;
}

/** GET /board. The gateway sends every column key, even when empty. */
export interface Board {
  columns: Record<BoardColumn, Card[]>;
}

export type ArtifactKind = "pr" | "diff" | "pptx" | "xlsx" | "link";

export interface Artifact {
  kind: ArtifactKind;
  /** Always an absolute URL (agreed with A), e.g. http://localhost:8000/artifacts/fix.diff */
  url: string;
  label: string;
}

/** GET /tasks/{task_id} */
export interface TaskDetail {
  task_id: string;
  title: string;
  assignee_role: string | null;
  status: Status;
  result_summary: string | null; // null until a RESULT: comment exists
  artifacts: Artifact[];
}

// ---- SSE: GET /events ----

export type AgentState = "idle" | "working" | "on_call";

export const SSE_EVENT_TYPES = ["agent.status", "task.updated", "task.completed", "ping"] as const;

export type ServerEvent =
  | { type: "agent.status"; role: string; state: AgentState }
  | { type: "task.updated"; task_id: string; status: Status; assignee_role: string | null; title: string }
  /** failed: the agent's run failed, so there's no result (only present on failures). */
  | { type: "task.completed"; task_id: string; from_role: string; title: string; summary: string; failed?: boolean }
  /** to_role = the active call's role when injected into a call; null when no call was active. */
  | { type: "ping"; to_role: string | null; from_role: string; task_id: string; text: string }
  /** Client-only: emitted after the SSE stream reconnects. Refetch /board and /roles. */
  | { type: "resync" };

// ---- WS /call/{role_id} ----

export const CALL_EVENT_TYPES = [
  "call.started",
  "transcript.user",
  "transcript.assistant.delta",
  "transcript.assistant.done",
  "agent.speaking",
  "barge_in",
  "tool.called",
  "task.started",
  "avatar.clip",
  "avatar.room",
  "avatar.unavailable",
  "call.ended",
] as const;

/** JSON text frames from the gateway. Binary frames are PCM16 24 kHz mono assistant audio
 *  (for a role with an avatar, replies come as `avatar.clip` MP4s with the audio inside instead). */
export type CallEvent =
  | { type: "call.started"; role: string }
  | { type: "transcript.user"; text: string }
  | { type: "transcript.assistant.delta"; text: string }
  | { type: "transcript.assistant.done"; text: string }
  | { type: "agent.speaking"; value: boolean }
  | { type: "barge_in" }
  | { type: "tool.called"; name: string; args: Record<string, unknown> }
  | { type: "task.started"; task_id: string; title: string; assignee_role: string }
  | { type: "avatar.clip"; url: string; duration: number }
  /** LiveKit room where the live avatar publishes its video and voice; join with this subscribe-only token. */
  | { type: "avatar.room"; url: string; token: string; avatar_identity: string }
  /** The live avatar couldn't start (busy: Boson had no free slot); the call continues as plain audio. */
  | { type: "avatar.unavailable"; reason: "busy" | "error" }
  | { type: "call.ended"; reason: string };

/** Close code the gateway uses when a second call is opened while one is active. */
export const CLOSE_ALREADY_ON_CALL = 4409;
/** Close code for a role id the gateway doesn't know. */
export const CLOSE_UNKNOWN_ROLE = 4404;

// ---- Client interfaces (implemented by api/gateway.ts and api/mock.ts) ----

export interface CallSocket {
  /** PCM16 24 kHz mono mic audio. Dropped if the socket isn't open yet. */
  sendAudio(pcm: ArrayBuffer): void;
  hangup(): void;
  onAudio(cb: (pcm: ArrayBuffer) => void): void;
  onEvent(cb: (e: CallEvent) => void): void;
  onClose(cb: (code: number) => void): void;
}

export interface Gateway {
  fetchRoles(): Promise<Role[]>;
  fetchBoard(): Promise<Board>;
  fetchTask(id: string): Promise<TaskDetail>;
  fetchAgentStatus(roleId: string): Promise<AgentStatusDetail>;
  /** Returns an unsubscribe function. */
  subscribe(onEvent: (e: ServerEvent) => void): () => void;
  /** video: a video call with the role's live avatar (the gateway sends `avatar.room`). */
  openCall(roleId: string, opts?: { video?: boolean }): CallSocket;
}
