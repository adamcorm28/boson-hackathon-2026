import { describe, expect, it } from "vitest";
import { BOARD_COLUMNS, type Board, type Card, type Role } from "../api/types";
import { buildContacts, moveSelection, type ContactInputs } from "./contacts";

const role = (id: string, name: string, title = ""): Role => ({ id, name, title, reports_to: null, voice: "default" });
const ROLES = [
  role("ceo", "Michael Scott", "Regional Manager"),
  role("engineer", "Dwight Schrute", "Engineer"),
  role("sales_lead", "Jim Halpert", "Sales Lead"),
];

function board(...cards: Card[]): Board {
  const columns = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, [] as Card[]])) as Board["columns"];
  for (const c of cards) columns[c.status as keyof Board["columns"]].push(c);
  return { columns };
}
const card = (task_id: string, title: string, assignee_role: string): Card => ({
  task_id,
  title,
  assignee_role,
  status: "in_progress",
  origin: "voice",
});
const none: ContactInputs = { agents: {}, bang: {}, ringing: {}, board: null, onLine: null };

describe("buildContacts", () => {
  it("lists everyone, sorted by first name like a phone", () => {
    const list = buildContacts(ROLES, none);
    expect(list.map((c) => c.firstName)).toEqual(["Dwight", "Jim", "Michael"]);
    expect(list[0]).toMatchObject({ roleId: "engineer", name: "Dwight Schrute", title: "Engineer", status: "idle", statusText: "Available" });
  });

  it("says what someone is working on, from the board", () => {
    const list = buildContacts(ROLES, { ...none, board: board(card("DM-111", "Fix bulk discount", "engineer"), card("DM-112", "Tests", "engineer")) });
    expect(list.find((c) => c.roleId === "engineer")).toMatchObject({
      status: "working",
      statusText: "Working on: Fix bulk discount (+1 more)",
    });
  });

  it("falls back to a plain 'Working' from agent.status alone", () => {
    const list = buildContacts(ROLES, { ...none, agents: { sales_lead: "working" } });
    expect(list.find((c) => c.roleId === "sales_lead")?.statusText).toBe("Working");
  });

  it("marks who you're on a call with, and who's on another call", () => {
    const list = buildContacts(ROLES, { ...none, onLine: "ceo", agents: { engineer: "on_call" }, board: board(card("A", "x", "ceo")) });
    expect(list.find((c) => c.roleId === "ceo")).toMatchObject({ status: "on_call", statusText: "On a call with you" });
    expect(list.find((c) => c.roleId === "engineer")).toMatchObject({ status: "busy", statusText: "On another call" });
  });

  it("carries unseen results and missed calls", () => {
    const list = buildContacts(ROLES, { ...none, bang: { engineer: ["DM-111"] }, ringing: { engineer: true } });
    expect(list.find((c) => c.roleId === "engineer")).toMatchObject({ unseen: ["DM-111"], missedCall: true });
    expect(list.find((c) => c.roleId === "ceo")).toMatchObject({ unseen: [], missedCall: false });
  });

  it("includes roles the office has no desk for", () => {
    const list = buildContacts([...ROLES, role("reception", "Pam Beesly")], none);
    expect(list.map((c) => c.firstName)).toContain("Pam");
  });
});

describe("moveSelection", () => {
  it("moves and stops at the ends", () => {
    expect(moveSelection(0, 1, 3)).toBe(1);
    expect(moveSelection(2, 1, 3)).toBe(2);
    expect(moveSelection(0, -1, 3)).toBe(0);
  });

  it("is safe on an empty list", () => {
    expect(moveSelection(0, 1, 0)).toBe(0);
  });
});
