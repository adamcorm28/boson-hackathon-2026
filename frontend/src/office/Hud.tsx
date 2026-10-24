// Side HUD: a minimap of the whiteboard (cards per column + what's in progress), so the audience
// sees cards move during calls. Toasts render here too.
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
            const n = board?.columns[col].length ?? 0;
            return (
              <div key={col} className={`hud-col ${col}`}>
                <span className="hud-label">{LABELS[col]}</span>
                <span className="hud-bar" style={{ width: `${(n / max) * 100}%` }} />
                <span className="hud-count">{n}</span>
              </div>
            );
          })}
        </div>
        <div className="hud-section">IN PROGRESS</div>
        {board?.columns.in_progress.length ? (
          <ul className="hud-cards">
            {board.columns.in_progress.map((c) => (
              <li key={c.task_id} className={c.origin}>
                {c.title} <span className="muted">· {first(c.assignee_role)}</span>
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
