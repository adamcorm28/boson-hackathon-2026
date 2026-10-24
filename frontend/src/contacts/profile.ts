// A contact's profile, as plain data: who they work with, their tasks, and how it's going.
import { BOARD_COLUMNS, type Board, type BoardColumn, type Card, type Role } from "../api/types";
import type { Contact } from "./contacts";

export type Tone = "good" | "warn" | "bad" | "info";

export interface Highlight {
  tone: Tone;
  text: string;
}

export interface Profile {
  manager: Role | null;
  reports: Role[];
  responsibilities: string[];
  counts: Record<BoardColumn, number>;
  /** Their open work, most urgent first: blocked, in progress, in review, to do. */
  open: Card[];
  done: Card[];
  /** What they're doing, in one line. */
  now: string;
  /** How it's going: blockers, results, what's done. */
  progress: Highlight[];
}

const OPEN_ORDER: BoardColumn[] = ["blocked", "in_progress", "in_review", "todo", "backlog"];
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function buildProfile(role: Role, roles: Role[], board: Board | null, contact: Contact): Profile {
  const mine = (col: BoardColumn) => board?.columns[col].filter((c) => c.assignee_role === role.id) ?? [];
  const counts = Object.fromEntries(BOARD_COLUMNS.map((col) => [col, mine(col).length])) as Record<BoardColumn, number>;
  const open = OPEN_ORDER.flatMap(mine);
  const inProgress = mine("in_progress");
  const blocked = mine("blocked");
  const inReview = mine("in_review");
  const done = mine("done");

  let now = "Available";
  if (contact.status === "on_call") now = "On a call with you right now";
  else if (contact.status === "busy") now = "On another call";
  else if (inProgress.length) {
    const more = inProgress.length > 1 ? ` (+${inProgress.length - 1} more)` : "";
    now = `Working on ${inProgress[0].title}${more}`;
  } else if (contact.status === "working") now = "Working";

  const highlights: Highlight[] = [];
  if (blocked.length) {
    highlights.push({ tone: "bad", text: `${plural(blocked.length, "task")} blocked: ${blocked.map((c) => c.title).join(", ")}` });
  }
  if (inReview.length) highlights.push({ tone: "warn", text: `${plural(inReview.length, "task")} waiting for review` });
  if (contact.unseen.length) {
    highlights.push({ tone: "good", text: `${plural(contact.unseen.length, "finished result")} waiting for you` });
  }
  if (contact.missedCall) highlights.push({ tone: "warn", text: "Tried to reach you while you were away" });
  if (done.length) highlights.push({ tone: "good", text: `${plural(done.length, "task")} done` });
  const notStarted = counts.todo + counts.backlog;
  if (notStarted) highlights.push({ tone: "info", text: `${plural(notStarted, "task")} not started yet` });
  if (!inProgress.length && !blocked.length && !inReview.length && !notStarted && !contact.unseen.length) {
    highlights.push({ tone: "info", text: "Nothing on their plate right now" });
  }

  return {
    manager: roles.find((r) => r.id === role.reports_to) ?? null,
    reports: roles.filter((r) => r.reports_to === role.id),
    responsibilities: role.responsibilities ?? [],
    counts,
    open,
    done,
    now,
    progress: highlights,
  };
}
