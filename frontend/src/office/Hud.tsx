// Side HUD: a miniature of the conference-room whiteboard, so the audience sees cards move during
// calls. One square per task, colored by its owner. Click it (or press B) for the full board.
import { BOARD_COLUMNS, type Board, type Role } from "../api/types";
import { accentFor } from "../art/looks";
import { Toasts } from "../results/Toasts";
import type { Toast } from "./officeReducer";

const LABELS: Record<string, string> = {
  backlog: "Backlog",
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  done: "Done",
};

interface Props {
  board: Board | null;
  roles: Role[];
  /** task_id of the card that just moved: its square blinks. */
  justMoved: string | null;
  toasts: Toast[];
  onOpenBoard(): void;
  onOpenResult(taskId: string): void;
  onDismissToast(id: string): void;
}

export function Hud({ board, roles, justMoved, toasts, onOpenBoard, onOpenResult, onDismissToast }: Props) {
  const first = (id: string | null) => roles.find((r) => r.id === id)?.name.split(" ")[0] ?? id ?? "—";

  return (
    <>
      <aside
        className="hud"
        role="button"
        tabIndex={0}
        aria-label="Whiteboard summary. Open the full whiteboard"
        onClick={onOpenBoard}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpenBoard();
          }
        }}
      >
        <div className="hud-head">
          <span className="hud-title">WHITEBOARD</span>
          <span className="hud-open">
            click or <kbd>B</kbd>
          </span>
        </div>

        <div className="hud-rows">
          {BOARD_COLUMNS.map((col) => {
            const cards = board?.columns[col] ?? [];
            return (
              <div key={col} className={`hud-row ${col}`}>
                <span className="hud-label">{LABELS[col]}</span>
                <span className="hud-notes">
                  {cards.map((c) => (
                    <span
                      key={c.task_id}
                      className={`hud-note ${c.origin} ${c.task_id === justMoved ? "moved" : ""}`}
                      style={{ background: c.assignee_role ? accentFor(c.assignee_role) : "#999" }}
                      title={`${c.title} · ${first(c.assignee_role)}`}
                    />
                  ))}
                </span>
                <span className="hud-count">{cards.length}</span>
              </div>
            );
          })}
        </div>
        <div className="hud-caption">each square is a task, colored by who owns it</div>

        <div className="hud-section">IN PROGRESS NOW</div>
        {board?.columns.in_progress.length ? (
          <ul className="hud-cards">
            {board.columns.in_progress.map((c) => (
              <li key={c.task_id} className={c.origin} style={{ borderLeftColor: c.assignee_role ? accentFor(c.assignee_role) : undefined }}>
                {c.title} <span className="hud-who">· {first(c.assignee_role)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hud-empty">Nothing right now.</p>
        )}
      </aside>
      <Toasts toasts={toasts} onOpen={onOpenResult} onDismiss={onDismissToast} />
    </>
  );
}
