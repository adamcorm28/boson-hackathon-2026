// Opening title card. Enter, Space, Esc or a click starts. Skip it with ?notitle in the URL.
import { useOverlayKeys } from "./useOverlayKeys";

export function TitleCard({ onStart, mock }: { onStart(): void; mock: boolean }) {
  useOverlayKeys(true, onStart, ["enter", " "]);

  return (
    <div className="titlecard" onClick={onStart} role="dialog" aria-label="Title">
      <div className="titlecard-inner">
        <div className="titlecard-company">DUNDER MIFFLIN</div>
        <div className="titlecard-product">
          INFINITY VOICE<sup>™</sup>
        </div>
        <div className="titlecard-sub">Scranton Branch · call your AI employees</div>
        <div className="titlecard-start">PRESS ENTER</div>
        <ul className="titlecard-keys">
          <li>
            <kbd>←↑↓→</kbd> walk
          </li>
          <li>
            <kbd>E</kbd> call someone at their desk
          </li>
          <li>
            <kbd>Esc</kbd> hang up
          </li>
          <li>
            <kbd>B</kbd> whiteboard
          </li>
        </ul>
        {mock && <div className="titlecard-mock">mock gateway</div>}
      </div>
    </div>
  );
}
