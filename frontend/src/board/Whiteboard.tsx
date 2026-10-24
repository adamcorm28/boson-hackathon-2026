// Full-screen conference-room whiteboard: six columns, cards colored by their owner,
// and a highlight on the card that just moved. Click a card to see its result.
import { BOARD_COLUMNS, type Board, type Role } from "../api/types";
import { lookFor } from "../art/looks";
import { useOverlayKeys } from "../ui/useOverlayKeys";

const LABELS: Record<string, string> = {
  backlog: "BACKLOG",
  todo: "TO DO",
  in_progress: "IN PROGRESS",
  in_review: "IN REVIEW",
  blocked: "BLOCKED",
  done: "DONE",
};

interface Props {
  board: Board | null;
  roles: Role[];
  /** task_id of the card that just moved (highlighted briefly). */
  justMoved: string | null;
  onOpenCard(taskId: string): void;
  onClose(): void;
}

export function Whiteboard({ board, roles, justMoved, onOpenCard, onClose }: Props) {
  useOverlayKeys(true, onClose, ["b"]);
  const first = (id: string | null) => roles.find((r) => r.id === id)?.name.split(" ")[0] ?? id ?? "unassigned";

  return (
    <div className="overlay" onClick={onClose}>
      <div className="whiteboard" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Whiteboard">
        <div className="wb-head">
          <h2>SCRANTON BRANCH · TASKS</h2>
          <button onClick={onClose}>
            Close <kbd>Esc</kbd>
          </button>
        </div>
        {!board && <p className="muted">Loading the board…</p>}
        {board && (
          <div className="wb-columns">
            {BOARD_COLUMNS.map((col) => (
              <section key={col} className={`wb-col ${col}`}>
                <h3>
                  {LABELS[col]} <span className="muted">{board.columns[col].length}</span>
                </h3>
                {board.columns[col].map((card) => {
                  const color = card.assignee_role ? lookFor(card.assignee_role).shirt : "#999";
                  return (
                    <button
                      key={`${card.task_id}-${col}`}
                      className={`wb-card ${card.task_id === justMoved ? "moved" : ""} ${card.origin}`}
                      style={{ borderLeftColor: color }}
                      onClick={() => onOpenCard(card.task_id)}
                    >
                      <span className="wb-card-title">{card.title}</span>
                      <span className="wb-card-meta">
                        <span className="wb-dot" style={{ background: color }} /> {first(card.assignee_role)}
                        {card.origin === "voice" && <span className="wb-voice"> · 🎙 from a call</span>}
                      </span>
                    </button>
                  );
                })}
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
