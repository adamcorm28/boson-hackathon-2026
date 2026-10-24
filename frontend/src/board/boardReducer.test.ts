import { describe, expect, it } from "vitest";
import { BOARD_COLUMNS, type Board, type Card, type ServerEvent, type Status } from "../api/types";
import { boardReducer } from "./boardReducer";

const card = (task_id: string, status: Status, extra: Partial<Card> = {}): Card => ({
  task_id,
  title: task_id,
  assignee_role: "engineer",
  status,
  origin: "seed",
  ...extra,
});

function board(...cards: Card[]): Board {
  const columns = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, [] as Card[]])) as Board["columns"];
  for (const c of cards) columns[c.status as keyof Board["columns"]].push(c);
  return { columns };
}

const updated = (task_id: string, status: Status, title = task_id, assignee_role: string | null = "engineer"): ServerEvent => ({
  type: "task.updated",
  task_id,
  status,
  title,
  assignee_role,
});

const where = (b: Board, id: string) => BOARD_COLUMNS.filter((c) => b.columns[c].some((x) => x.task_id === id));

describe("boardReducer", () => {
  it("task.updated moves card between columns", () => {
    const b = boardReducer(board(card("DM-101", "todo", { origin: "seed" }), card("DM-102", "todo")), updated("DM-101", "in_progress"));
    expect(where(b, "DM-101")).toEqual(["in_progress"]);
    expect(b.columns.in_progress[0]).toMatchObject({ task_id: "DM-101", status: "in_progress", origin: "seed" });
    expect(b.columns.todo.map((c) => c.task_id)).toEqual(["DM-102"]);
  });

  it("new task inserted", () => {
    const b = boardReducer(board(), updated("DM-111", "todo", "Fix bulk discount"));
    expect(b.columns.todo).toEqual([
      { task_id: "DM-111", title: "Fix bulk discount", assignee_role: "engineer", status: "todo", origin: "voice" },
    ]);
  });

  it("card never in two columns", () => {
    let b = board(card("A", "todo"));
    for (const s of ["in_progress", "in_review", "in_progress", "done", "done", "blocked"] as Status[]) {
      b = boardReducer(b, updated("A", s));
      expect(where(b, "A")).toEqual([s]);
    }
  });

  it("a title or assignee change keeps the card where it is in its column", () => {
    const b = boardReducer(board(card("A", "todo"), card("B", "todo")), updated("A", "todo", "Renamed", "sales_lead"));
    expect(b.columns.todo.map((c) => [c.task_id, c.title, c.assignee_role])).toEqual([
      ["A", "Renamed", "sales_lead"],
      ["B", "B", "engineer"],
    ]);
  });

  it("cancelled cards are dropped (agreed with A)", () => {
    const b = boardReducer(board(card("A", "todo")), updated("A", "cancelled"));
    expect(where(b, "A")).toEqual([]);
  });

  it("does not mutate the input board", () => {
    const before = board(card("A", "todo"));
    const snapshot = JSON.stringify(before);
    boardReducer(before, updated("A", "done"));
    expect(JSON.stringify(before)).toBe(snapshot);
  });

  it("other events return the same board", () => {
    const b = board(card("A", "todo"));
    expect(boardReducer(b, { type: "resync" })).toBe(b);
    expect(boardReducer(b, { type: "agent.status", role: "engineer", state: "working" })).toBe(b);
  });
});
