import { describe, expect, it } from "vitest";
import { BOARD_COLUMNS, type Board, type Card, type Role, type Status } from "../api/types";
import type { Contact } from "./contacts";
import { buildProfile } from "./profile";

const role = (id: string, name: string, reports_to: string | null, responsibilities?: string[]): Role => ({
  id,
  name,
  title: "",
  reports_to,
  voice: "default",
  responsibilities,
});
const ROLES = [
  role("ceo", "Michael Scott", null),
  role("eng_lead", "Ryan Howard", "ceo", ["Owns Infinity"]),
  role("engineer", "Dwight Schrute", "eng_lead"),
];

const card = (task_id: string, status: Status, assignee_role = "engineer", title = task_id): Card => ({
  task_id,
  title,
  assignee_role,
  status,
  origin: "seed",
});
function board(...cards: Card[]): Board {
  const columns = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, [] as Card[]])) as Board["columns"];
  for (const c of cards) columns[c.status as keyof Board["columns"]].push(c);
  return { columns };
}
const contact = (over: Partial<Contact> = {}): Contact => ({
  roleId: "engineer",
  name: "Dwight Schrute",
  firstName: "Dwight",
  title: "",
  status: "idle",
  statusText: "Available",
  unseen: [],
  missedCall: false,
  ...over,
});
const dwight = ROLES[2];

describe("buildProfile", () => {
  it("finds the manager and direct reports", () => {
    const ryan = buildProfile(ROLES[1], ROLES, null, contact({ roleId: "eng_lead" }));
    expect(ryan.manager?.name).toBe("Michael Scott");
    expect(ryan.reports.map((r) => r.name)).toEqual(["Dwight Schrute"]);
    expect(ryan.responsibilities).toEqual(["Owns Infinity"]);
    expect(buildProfile(ROLES[0], ROLES, null, contact({ roleId: "ceo" })).manager).toBeNull();
  });

  it("counts only their own tasks and lists open work, most urgent first", () => {
    const b = board(
      card("T1", "todo"),
      card("P1", "in_progress"),
      card("B1", "blocked"),
      card("R1", "in_review"),
      card("D1", "done"),
      card("X1", "in_progress", "eng_lead"),
    );
    const p = buildProfile(dwight, ROLES, b, contact());
    expect(p.counts).toEqual({ backlog: 0, todo: 1, in_progress: 1, in_review: 1, blocked: 1, done: 1 });
    expect(p.open.map((c) => c.task_id)).toEqual(["B1", "P1", "R1", "T1"]);
    expect(p.done.map((c) => c.task_id)).toEqual(["D1"]);
  });

  it("says what they're doing and how it's going", () => {
    const b = board(card("P1", "in_progress", "engineer", "Fix bulk discount"), card("B1", "blocked", "engineer", "Tablet layout"), card("D1", "done"));
    const p = buildProfile(dwight, ROLES, b, contact({ status: "working", unseen: ["D1"], missedCall: true }));
    expect(p.now).toBe("Working on Fix bulk discount");
    expect(p.progress).toEqual([
      { tone: "bad", text: "1 task blocked: Tablet layout" },
      { tone: "good", text: "1 finished result waiting for you" },
      { tone: "warn", text: "Tried to reach you while you were away" },
      { tone: "good", text: "1 task done" },
    ]);
  });

  it("says when someone's free, has work queued, or is on a call", () => {
    const free = buildProfile(dwight, ROLES, board(), contact());
    expect(free.now).toBe("Available");
    expect(free.progress).toEqual([{ tone: "info", text: "Nothing on their plate right now" }]);

    const queued = buildProfile(dwight, ROLES, board(card("T1", "todo"), card("T2", "backlog")), contact());
    expect(queued.progress).toEqual([{ tone: "info", text: "2 tasks not started yet" }]);

    expect(buildProfile(dwight, ROLES, board(), contact({ status: "on_call" })).now).toBe("On a call with you right now");
    expect(buildProfile(dwight, ROLES, board(), contact({ status: "busy" })).now).toBe("On another call");
  });

  it("works without a board or responsibilities", () => {
    const p = buildProfile(dwight, ROLES, null, contact());
    expect(p.responsibilities).toEqual([]);
    expect(p.open).toEqual([]);
  });
});
