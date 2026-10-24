// Retro video-call window: portrait, waveform, live transcript, task chips, hang-up (Esc).
import { useEffect, useRef } from "react";
import type { Role } from "../api/types";
import type { CallState } from "./callReducer";
import { Portrait } from "./Portrait";

interface Props {
  state: CallState;
  roles: Role[];
  talking: boolean;
  onHangup(): void;
  onRetryMic(): void;
}

const firstName = (roles: Role[], id: string | null) => roles.find((r) => r.id === id)?.name.split(" ")[0] ?? id ?? "?";

const STATUS_TEXT: Record<CallState["status"], string> = {
  idle: "",
  connecting: "Ringing…",
  live: "● LIVE",
  ended: "Call ended",
};

export function CallWindow({ state, roles, talking, onHangup, onRetryMic }: Props) {
  const transcriptRef = useRef<HTMLDivElement>(null);
  const role = roles.find((r) => r.id === state.roleId);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onHangup();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onHangup]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [state.lines]);

  if (state.status === "idle" || !state.roleId) return null;
  const name = firstName(roles, state.roleId);

  return (
    <div className={`call-window ${state.status}`} role="dialog" aria-label={`Call with ${role?.name ?? name}`}>
      <div className="call-titlebar">
        <span>📞 {role?.name ?? name}</span>
        <span className={`call-status ${state.status}`}>
          {STATUS_TEXT[state.status]}
          {state.status === "ended" && state.endReason ? ` (${state.endReason.replace(/_/g, " ")})` : ""}
        </span>
      </div>

      <div className="call-body">
        <div className="call-left">
          <div className={`call-portrait ${talking ? "talking" : ""}`}>
            <Portrait roleId={state.roleId} talking={talking} />
          </div>
          <div className="call-role">{role?.title}</div>
          <div className={`waveform ${talking ? "on" : ""}`} aria-hidden>
            {Array.from({ length: 12 }, (_, i) => (
              <span key={i} style={{ animationDelay: `${(i * 97) % 600}ms` }} />
            ))}
          </div>
        </div>

        <div className="call-right">
          <div className="call-transcript" ref={transcriptRef}>
            {state.lines.length === 0 && <div className="muted">{state.status === "connecting" ? "Ringing…" : "…"}</div>}
            {state.lines.map((l, i) => (
              <div key={i} className={`line ${l.speaker} ${l.final ? "" : "partial"}`}>
                <b>{l.speaker === "user" ? "YOU" : name.toUpperCase()}:</b> {l.text}
              </div>
            ))}
          </div>

          {state.tasks.length > 0 && (
            <div className="call-chips">
              {state.tasks.map((t) => (
                <span key={t.task_id} className="chip">
                  📋 {t.title} → {firstName(roles, t.assignee_role)}
                </span>
              ))}
            </div>
          )}

          {state.error && <div className="call-error">{state.error}</div>}
          {state.micError && (
            <div className="call-error">
              {state.micError} <button onClick={onRetryMic}>Retry mic</button>
            </div>
          )}
        </div>
      </div>

      <div className="call-footer">
        <button className="hangup" onClick={onHangup}>
          {state.status === "ended" ? "Close" : "Hang up"} <kbd>Esc</kbd>
        </button>
      </div>
    </div>
  );
}
