// Applies SSE task updates to the board. `resync` is handled in App by refetching /board.
import { BOARD_COLUMNS, type Board, type BoardColumn, type Card, type ServerEvent } from "../api/types";

const isColumn = (s: string): s is BoardColumn => (BOARD_COLUMNS as readonly string[]).includes(s);

export function boardReducer(board: Board, e: ServerEvent): Board {
  if (e.type !== "task.updated") return board;

  let existing: Card | undefined;
  let existingCol: BoardColumn | undefined;
  for (const col of BOARD_COLUMNS) {
    const found = board.columns[col].find((c) => c.task_id === e.task_id);
    if (found) {
      existing = found;
      existingCol = col;
      break;
    }
  }

  const next: Card = {
    task_id: e.task_id,
    title: e.title,
    assignee_role: e.assignee_role,
    status: e.status,
    origin: existing?.origin ?? "voice", // new cards mid-demo come from delegate_task
  };

  // Same column: update in place so the card doesn't jump around.
  if (existingCol && existingCol === e.status) {
    return {
      columns: { ...board.columns, [existingCol]: board.columns[existingCol].map((c) => (c.task_id === e.task_id ? next : c)) },
    };
  }

  const columns = { ...board.columns };
  if (existingCol) columns[existingCol] = columns[existingCol].filter((c) => c.task_id !== e.task_id);
  if (isColumn(e.status)) columns[e.status] = [...columns[e.status], next]; // `cancelled` (or anything unknown) is dropped
  return { columns };
}
