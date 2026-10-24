// Video-call screen, centered over the office: the employee's tile (lip-synced avatar or pixel
// portrait) with live captions, your tile with the camera off, a transcript panel, and a
// control bar (mute, video off, transcript, leave with Esc).
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Role } from "../api/types";
import type { CallState } from "./callReducer";
import { Avatar } from "../ui/Avatar";
import { Portrait } from "./Portrait";

interface Props {
  state: CallState;
  roles: Role[];
  talking: boolean;
  /** Avatar videos from the call controller (live avatar or sync-mode clips). */
  media: HTMLElement | null;
  muted?: boolean;
  onToggleMute?(): void;
  onHangup(): void;
  onRetryMic(): void;
  /** Classic mode: a round initials avatar instead of the pixel portrait. */
  classic?: boolean;
}

const firstName = (roles: Role[], id: string | null) => roles.find((r) => r.id === id)?.name.split(" ")[0] ?? id ?? "?";

function useElapsed(live: boolean): string {
  const [start, setStart] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) {
      setStart(null);
      return;
    }
    setStart(Date.now());
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [live]);
  const secs = start ? Math.max(0, Math.floor((now - start) / 1000)) : 0;
  return `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
}

export function CallWindow({ state, roles, talking, media, muted = false, onToggleMute, onHangup, onRetryMic, classic = false }: Props) {
  const transcriptRef = useRef<HTMLDivElement>(null);
  const [showTranscript, setShowTranscript] = useState(true);
  const role = roles.find((r) => r.id === state.roleId);
  const elapsed = useElapsed(state.status === "live");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onHangup();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onHangup]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [state.lines, showTranscript]);

  if (state.status === "idle" || !state.roleId) return null;
  const name = firstName(roles, state.roleId);
  const fullName = role?.name ?? name;
  const caption = state.lines.at(-1);
  const face = classic ? (
    <Avatar roleId={state.roleId} name={fullName} size={168} className={`call-avatar ${talking ? "talking" : ""}`} />
  ) : (
    <Portrait roleId={state.roleId} talking={talking} pixel={20} />
  );

  return (
    <div className="zoom-backdrop">
      <div className={`zoom ${state.status}`} role="dialog" aria-label={`Call with ${fullName}`}>
        <header className="zoom-top">
          <span className="zoom-secure" title="End-to-end encrypted (it's a paper company)">
            <ShieldIcon />
          </span>
          <span className="zoom-title">Dunder Mifflin · {fullName}</span>
          <span className={`zoom-status ${state.status}`}>
            {state.status === "connecting" && "Connecting…"}
            {state.status === "live" && (
              <>
                <span className="zoom-rec" /> {elapsed}
              </>
            )}
            {state.status === "ended" &&
              `Call ended${state.endReason ? ` (${state.endReason.replace(/_/g, " ")})` : ""}`}
          </span>
        </header>

        <div className="zoom-main">
          <div className="zoom-stage">
            <div className={`zoom-tile speaker ${talking ? "talking" : ""}`}>
              {/* A live avatar replaces the reference image, which would otherwise flash before its video arrives. */}
              {role?.avatar_live || role?.avatar_url ? (
                <AvatarFace
                  still={role.avatar_live ? null : (role.avatar_url ?? null)}
                  loop={role.avatar_live ? null : (role.avatar_loop_url ?? null)}
                  idle={role.avatar_live ? null : (role.avatar_idle_url ?? null)}
                  talking={talking}
                  media={media}
                  name={fullName}
                  placeholder={face}
                />
              ) : (
                <div className="zoom-portrait">{face}</div>
              )}
              {state.status === "connecting" && <div className="zoom-ringing">Calling {name}…</div>}
              {state.videoNotice && <div className="zoom-video-notice">{state.videoNotice} · audio only</div>}
              <span className="zoom-name">
                <MicIcon off={false} /> {fullName}
                {role?.title && <span className="zoom-name-title"> · {role.title}</span>}
              </span>
              {caption && (
                <div className={`zoom-caption ${caption.final ? "" : "partial"}`}>
                  <b>{caption.speaker === "user" ? "You" : name}:</b> {caption.text}
                </div>
              )}
            </div>

            <div className="zoom-tile self">
              <div className="zoom-avatar-initials">YOU</div>
              <span className="zoom-name">
                <MicIcon off={muted} /> You
              </span>
              <span className="zoom-camoff" title="Camera off">
                <VideoIcon off />
              </span>
            </div>

            {(state.error || state.micError) && (
              <div className="zoom-banner">
                {state.error}
                {state.micError && (
                  <>
                    {state.micError} <button onClick={onRetryMic}>Retry mic</button>
                  </>
                )}
              </div>
            )}
          </div>

          {showTranscript && (
            <aside className="zoom-panel">
              <h3>Transcript</h3>
              <div className="zoom-transcript" ref={transcriptRef}>
                {state.lines.length === 0 && (
                  <div className="muted">{state.status === "connecting" ? "Waiting for them to join…" : "…"}</div>
                )}
                {state.lines.map((l, i) => (
                  <div key={i} className={`zoom-line ${l.speaker} ${l.final ? "" : "partial"}`}>
                    <b>{l.speaker === "user" ? "You" : name}</b>
                    <span>{l.text}</span>
                  </div>
                ))}
              </div>
              {state.tasks.length > 0 && (
                <div className="zoom-tasks">
                  <h3>Tasks started</h3>
                  {state.tasks.map((t) => (
                    <div key={t.task_id} className="zoom-task">
                      📋 {t.title} <span className="muted">→ {firstName(roles, t.assignee_role)}</span>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          )}
        </div>

        <footer className="zoom-controls">
          <div className="zoom-controls-left">
            <button
              className={`zoom-ctl ${muted ? "off" : ""}`}
              onClick={onToggleMute}
              disabled={!onToggleMute || state.status === "ended"}
            >
              <MicIcon off={muted} />
              <span>{muted ? "Unmute" : "Mute"}</span>
            </button>
            <button className="zoom-ctl off" disabled title="Your camera is off">
              <VideoIcon off />
              <span>Start Video</span>
            </button>
          </div>
          <div className="zoom-controls-mid">
            <button className={`zoom-ctl ${showTranscript ? "active" : ""}`} onClick={() => setShowTranscript((s) => !s)}>
              <ChatIcon />
              <span>Transcript</span>
            </button>
          </div>
          <button className="zoom-leave" onClick={onHangup}>
            {state.status === "ended" ? "Close" : "Leave"} <kbd>Esc</kbd>
          </button>
        </footer>
      </div>
    </div>
  );
}

interface AvatarFaceProps {
  /** Reference image; without one (live avatar only) the placeholder shows until the video arrives. */
  still: string | null;
  /** Talking loop, played muted over the still while the (live) voice plays. */
  loop: string | null;
  /** Listening loop, always playing under everything so the face keeps moving. */
  idle: string | null;
  talking: boolean;
  /** Controller's avatar videos: the live avatar, or sync-mode clips, each visible while it has a picture. */
  media: HTMLElement | null;
  name: string;
  placeholder: ReactNode;
}

/** The face: still image (or placeholder), with the live avatar, a clip or the talking loop over it. */
function AvatarFace({ still, loop, idle, talking, media, name, placeholder }: AvatarFaceProps) {
  const box = useRef<HTMLDivElement>(null);
  const loopRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || !media) return;
    el.appendChild(media);
    return () => media.remove();
  }, [media]);

  useEffect(() => {
    const el = loopRef.current;
    if (!el) return;
    if (talking) {
      void el.play().catch(() => {});
    } else {
      el.pause();
      el.currentTime = 0; // the loop starts from the reference pose
    }
  }, [talking]);

  return (
    <div className="avatar-face" ref={box}>
      {still ? <img src={still} alt={name} /> : <div className="avatar-placeholder">{placeholder}</div>}
      {idle && <video className="avatar-video avatar-idle on" src={idle} muted loop autoPlay playsInline preload="auto" />}
      {loop && <video ref={loopRef} className={`avatar-video ${talking ? "on" : ""}`} src={loop} muted loop playsInline preload="auto" />}
    </div>
  );
}

// ---- icons (inline, so they follow currentColor) ----

function MicIcon({ off }: { off: boolean }) {
  return (
    <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
      {off && <path d="M4 4l16 16" stroke="#ff5f57" strokeWidth="2.5" strokeLinecap="round" />}
    </svg>
  );
}

function VideoIcon({ off }: { off: boolean }) {
  return (
    <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
      <rect x="3" y="7" width="12" height="10" rx="2" fill="currentColor" />
      <path d="M15 11l6-3v8l-6-3z" fill="currentColor" />
      {off && <path d="M4 4l16 16" stroke="#ff5f57" strokeWidth="2.5" strokeLinecap="round" />}
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
      <path d="M4 5h16v10H9l-5 4z" fill="currentColor" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
      <path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z" fill="currentColor" />
    </svg>
  );
}
