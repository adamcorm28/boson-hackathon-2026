// Side HUD: a minimap of the whiteboard (cards per column + what's in progress), so the audience
// sees cards move during calls. Hovering a column shows its cards; clicking opens the whiteboard.
// Toasts render here too.
import { BOARD_COLUMNS, type Board, type Role } from "../api/types";
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
/** Cards listed in a column's hover popover; the rest are summarized as "+N more". */
const PEEK_CARDS = 6;

interface Props {
  board: Board | null;
  roles: Role[];
  toasts: Toast[];
  onOpenBoard(): void;
  onOpenResult(taskId: string): void;
  onDismissToast(id: string): void;
}

export function Hud({ board, roles, toasts, onOpenBoard, onOpenResult, onDismissToast }: Props) {
  const first = (id: string | null) => roles.find((r) => r.id === id)?.name.split(" ")[0] ?? id ?? "—";
  const max = Math.max(1, ...BOARD_COLUMNS.map((c) => board?.columns[c].length ?? 0));

  return (
    <>
      <aside className="hud">
        <button className="hud-title" onClick={onOpenBoard} title="Open the whiteboard (B)">
          WHITEBOARD <kbd>B</kbd>
        </button>
        <div className="hud-columns">
          {BOARD_COLUMNS.map((col) => {
            const cards = board?.columns[col] ?? [];
            const n = cards.length;
            return (
              <button
                key={col}
                className={`hud-col ${col}`}
                onClick={onOpenBoard}
                aria-label={`${LABELS[col]}: ${n} ${n === 1 ? "card" : "cards"}. Open the whiteboard`}
              >
                <span className="hud-label">{LABELS[col]}</span>
                <span className="hud-bar" style={{ width: `${(n / max) * 100}%` }} />
                <span className="hud-count">{n}</span>
                <span className="hud-peek" role="tooltip">
                  <span className="hud-peek-head">
                    {LABELS[col]} · {n}
                  </span>
                  {n === 0 && <span className="muted">Nothing here.</span>}
                  {cards.slice(0, PEEK_CARDS).map((c) => (
                    <span key={c.task_id} className={`hud-peek-card ${c.origin}`}>
                      {c.title} <span className="muted">· {first(c.assignee_role)}</span>
                    </span>
                  ))}
                  {n > PEEK_CARDS && <span className="muted">+{n - PEEK_CARDS} more</span>}
                  <span className="hud-peek-hint muted">Click to open the whiteboard</span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="hud-section">IN PROGRESS</div>
        {board?.columns.in_progress.length ? (
          <ul className="hud-cards">
            {board.columns.in_progress.map((c) => (
              <li key={c.task_id} className={c.origin}>
                <button className="hud-card" onClick={onOpenBoard} title="Open the whiteboard (B)">
                  {c.title} <span className="muted">· {first(c.assignee_role)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted hud-empty">Nothing right now.</p>
        )}
      </aside>
      <Toasts toasts={toasts} onOpen={onOpenResult} onDismiss={onDismissToast} />
    </>
  );
}
