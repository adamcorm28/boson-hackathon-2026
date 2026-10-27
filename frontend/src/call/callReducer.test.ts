import { describe, expect, it } from "vitest";
import type { CallEvent } from "../api/types";
import {
  ALREADY_ON_CALL_TEXT,
  callReducer,
  initialCallState,
  MIC_BLOCKED_TEXT,
  UNKNOWN_ROLE_TEXT,
  type CallAction,
  type CallState,
} from "./callReducer";

const run = (...actions: CallAction[]): CallState => actions.reduce(callReducer, initialCallState);
const live = (...actions: CallAction[]) =>
  run({ type: "dial", roleId: "ceo" }, { type: "call.started", role: "ceo" }, ...actions);

describe("callReducer", () => {
  it("dial then call.started goes connecting -> live", () => {
    expect(run({ type: "dial", roleId: "ceo" })).toMatchObject({ status: "connecting", roleId: "ceo" });
    expect(live().status).toBe("live");
  });

  it("delta then done builds one agent line", () => {
    const s = live(
      { type: "transcript.assistant.delta", text: "Michael" },
      { type: "transcript.assistant.delta", text: " Scott." },
      { type: "transcript.assistant.done", text: "Michael Scott." },
    );
    expect(s.lines).toEqual([{ speaker: "agent", text: "Michael Scott.", final: true }]);
  });

  it("a delta after a finished line starts a new line", () => {
    const s = live(
      { type: "transcript.assistant.done", text: "One." },
      { type: "transcript.assistant.delta", text: "Two" },
    );
    expect(s.lines).toEqual([
      { speaker: "agent", text: "One.", final: true },
      { speaker: "agent", text: "Two", final: false },
    ]);
  });

  it("a late user transcript goes before the agent line already in progress", () => {
    const s = live(
      { type: "transcript.assistant.delta", text: "Sure" },
      { type: "transcript.user", text: "Fix the discount" },
      { type: "transcript.assistant.delta", text: " thing." },
    );
    expect(s.lines).toEqual([
      { speaker: "user", text: "Fix the discount", final: true },
      { speaker: "agent", text: "Sure thing.", final: false },
    ]);
  });

  it("barge_in closes the interrupted line so the next reply starts fresh", () => {
    const s = live(
      { type: "agent.speaking", value: true },
      { type: "transcript.assistant.delta", text: "Let me tell you about" },
      { type: "barge_in" },
      { type: "transcript.assistant.delta", text: "Yes?" },
    );
    expect(s.speaking).toBe(false);
    expect(s.lines).toEqual([
      { speaker: "agent", text: "Let me tell you about", final: true },
      { speaker: "agent", text: "Yes?", final: false },
    ]);
  });

  it("task.started adds chip", () => {
    const started: CallEvent = { type: "task.started", task_id: "DM-111", title: "Fix bulk discount", assignee_role: "engineer" };
    const s = live(started, started);
    expect(s.tasks).toEqual([{ task_id: "DM-111", title: "Fix bulk discount", assignee_role: "engineer" }]);
  });

  it("call.ended sets ended", () => {
    const s = live({ type: "agent.speaking", value: true }, { type: "call.ended", reason: "idle_timeout" });
    expect(s).toMatchObject({ status: "ended", speaking: false, endReason: "idle_timeout", error: null });
  });

  it("4409 sets already-on-call error", () => {
    const s = run({ type: "dial", roleId: "ceo" }, { type: "closed", code: 4409 });
    expect(s).toMatchObject({ status: "ended", error: ALREADY_ON_CALL_TEXT });
  });

  it("4404 says the employee is unknown", () => {
    const s = run({ type: "dial", roleId: "pam" }, { type: "closed", code: 4404 });
    expect(s).toMatchObject({ status: "ended", error: UNKNOWN_ROLE_TEXT });
  });

  it("a normal close just ends; an abnormal one says the connection was lost", () => {
    expect(live({ type: "closed", code: 1000 })).toMatchObject({ status: "ended", error: null });
    expect(live({ type: "closed", code: 1006 }).error).toMatch(/lost connection/i);
  });

  it("mic_blocked shows the retry message, mic_ok clears it", () => {
    const blocked = live({ type: "mic_blocked" });
    expect(blocked.micError).toBe(MIC_BLOCKED_TEXT);
    expect(blocked.status).toBe("live"); // you can still hear them
    expect(callReducer(blocked, { type: "mic_ok" }).micError).toBeNull();
  });

  it("dismiss returns to idle, and a new dial starts clean", () => {
    const s = live({ type: "transcript.user", text: "hi" }, { type: "closed", code: 1000 });
    expect(callReducer(s, { type: "dismiss" })).toEqual(initialCallState);
    expect(callReducer(s, { type: "dial", roleId: "cfo" })).toMatchObject({ status: "connecting", roleId: "cfo", lines: [] });
  });

  it("unknown event ignored", () => {
    const s = live();
    expect(callReducer(s, { type: "mystery.event" } as unknown as CallAction)).toBe(s);
    expect(callReducer(s, { type: "tool.called", name: "get_board", args: {} })).toBe(s);
  });

  it("ignores call events when no call is open", () => {
    expect(callReducer(initialCallState, { type: "transcript.user", text: "hello?" })).toBe(initialCallState);
    const ended = live({ type: "closed", code: 1000 });
    expect(callReducer(ended, { type: "transcript.assistant.delta", text: "late" })).toBe(ended);
  });

  it("avatar.unavailable explains the missing video", () => {
    const s = callReducer({ ...initialCallState, status: "live", roleId: "ceo" }, { type: "avatar.unavailable", reason: "busy" });
    expect(s.videoNotice).toMatch(/busy/);
  });

  it("voice.fallback says they're not in the cloned voice", () => {
    const s = callReducer({ ...initialCallState, status: "live", roleId: "ceo" }, { type: "voice.fallback", voice: "marcus", wanted: "voice_abc" });
    expect(s.voiceNotice).toMatch(/preset "marcus"/);
    expect(callReducer(s, { type: "dial", roleId: "cfo" }).voiceNotice).toBeNull();
  });
});

describe("attachments", () => {
  const attachment: CallEvent = {
    type: "attachment",
    task_id: "DUNA-20",
    title: "Research: competitor financials",
    artifacts: [{ kind: "pdf", url: "http://localhost:8000/artifacts/r.pdf", label: "Competitor report" }],
  };

  it("an attachment event adds the files to the call", () => {
    const s = live(attachment);
    expect(s.attachments).toEqual([{ task_id: "DUNA-20", title: "Research: competitor financials", artifacts: attachment.type === "attachment" ? attachment.artifacts : [] }]);
  });

  it("the same attachment twice is shown once", () => {
    expect(live(attachment, attachment).attachments).toHaveLength(1);
  });

  it("a new call starts without attachments", () => {
    expect(run({ type: "dial", roleId: "cfo" }).attachments).toEqual([]);
  });
});
