// Picked before a call starts: audio (voice only, the fastest) or video (Boson live avatar,
// lip-synced). A for audio, V for video, Esc cancels.
import { useEffect, useRef } from "react";
import type { Role } from "../api/types";
import { useOverlayKeys } from "../ui/useOverlayKeys";
import { Portrait } from "./Portrait";

interface Props {
  role: Role;
  onChoose(video: boolean): void;
  onCancel(): void;
}

export const canVideoCall = (role: Role) => Boolean(role.avatar_live || role.avatar_url);

export function CallChooser({ role, onChoose, onCancel }: Props) {
  useOverlayKeys(true, onCancel);
  const video = canVideoCall(role);
  const choose = useRef(onChoose);
  choose.current = onChoose;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      if (key === "a" || key === "1") choose.current(false);
      else if ((key === "v" || key === "2") && video) choose.current(true);
      else return;
      e.preventDefault();
      e.stopImmediatePropagation();
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [video]);

  return (
    <div className="zoom-backdrop" onClick={onCancel}>
      <div className="zoom chooser" role="dialog" aria-label={`Call ${role.name}`} onClick={(e) => e.stopPropagation()}>
        <div className="chooser-who">
          <div className="chooser-portrait">
            <Portrait roleId={role.id} talking={false} pixel={7} />
          </div>
          <div>
            <div className="chooser-name">{role.name}</div>
            <div className="muted">{role.title}</div>
          </div>
        </div>
        <div className="chooser-options">
          <button className="chooser-option" onClick={() => onChoose(false)} autoFocus>
            <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
              <path
                d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"
                fill="currentColor"
              />
            </svg>
            <span>Audio call</span>
            <kbd>A</kbd>
          </button>
          <button
            className="chooser-option video"
            onClick={() => onChoose(true)}
            disabled={!video}
            title={video ? undefined : "No video avatar set up for them"}
          >
            <svg className="zoom-icon" viewBox="0 0 24 24" aria-hidden>
              <rect x="3" y="7" width="12" height="10" rx="2" fill="currentColor" />
              <path d="M15 11l6-3v8l-6-3z" fill="currentColor" />
            </svg>
            <span>Video call</span>
            <kbd>V</kbd>
          </button>
        </div>
        <button className="chooser-cancel" onClick={onCancel}>
          Cancel <kbd>Esc</kbd>
        </button>
      </div>
    </div>
  );
}
