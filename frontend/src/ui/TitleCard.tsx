// Opening title card with the mode choice. ←/→ picks a mode, Enter (or Space/Esc) starts,
// clicking a mode starts in it. Skip the card with ?notitle in the URL.
import { useEffect, useRef } from "react";
import { otherMode, type Mode } from "../modes";
import { useOverlayKeys } from "./useOverlayKeys";

interface Props {
  mode: Mode;
  onModeChange(mode: Mode): void;
  onStart(): void;
  mock: boolean;
}

const MODES: { id: Mode; name: string; blurb: string }[] = [
  { id: "arcade", name: "ARCADE", blurb: "walk the office, press E at a desk" },
  { id: "classic", name: "CLASSIC", blurb: "phone contact list, click to call" },
];

const KEYS: Record<Mode, [string, string][]> = {
  arcade: [
    ["←↑↓→", "walk"],
    ["E", "call someone at their desk"],
    ["Esc", "hang up"],
    ["B", "whiteboard"],
  ],
  classic: [
    ["↑↓", "pick someone"],
    ["Enter", "call"],
    ["Esc", "hang up"],
    ["B", "whiteboard"],
  ],
};

export function TitleCard({ mode, onModeChange, onStart, mock }: Props) {
  useOverlayKeys(true, onStart, ["enter", " "]);

  // Arrow keys switch the mode while the card is up (and don't reach the office underneath).
  const live = useRef({ mode, onModeChange });
  live.current = { mode, onModeChange };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      live.current.onModeChange(otherMode(live.current.mode));
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, []);

  return (
    <div className="titlecard" onClick={onStart} role="dialog" aria-label="Title">
      <div className="titlecard-inner">
        <div className="titlecard-company">DUNDER MIFFLIN</div>
        <div className="titlecard-product">
          INFINITY VOICE<sup>™</sup>
        </div>
        <div className="titlecard-sub">Scranton Branch · call your AI employees</div>

        <div className="titlecard-modes" role="radiogroup" aria-label="Mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="radio"
              aria-checked={mode === m.id}
              className={`titlecard-mode ${mode === m.id ? "selected" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                onModeChange(m.id);
                onStart();
              }}
            >
              <span className="titlecard-mode-name">
                {mode === m.id ? "▶ " : ""}
                {m.name}
              </span>
              <span className="titlecard-mode-blurb">{m.blurb}</span>
            </button>
          ))}
        </div>

        <div className="titlecard-start">PRESS ENTER</div>
        <ul className="titlecard-keys">
          {KEYS[mode].map(([k, what]) => (
            <li key={k}>
              <kbd>{k}</kbd> {what}
            </li>
          ))}
          <li>
            <kbd>M</kbd> switch mode
          </li>
        </ul>
        {mock && <div className="titlecard-mock">mock gateway</div>}
      </div>
    </div>
  );
}
