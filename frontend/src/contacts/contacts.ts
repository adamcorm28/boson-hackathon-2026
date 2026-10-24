// Classic mode's phone contact list, as plain data: who's there, what they're doing, what's waiting for you.
import type { AgentState, Board, Role } from "../api/types";

export type ContactStatus = "on_call" | "busy" | "working" | "idle";

export interface Contact {
  roleId: string;
  name: string;
  firstName: string;
  title: string;
  status: ContactStatus;
  /** One line under the name, e.g. "Working on: Fix bulk discount". */
  statusText: string;
  /** Finished task ids you haven't opened yet. */
  unseen: string[];
  /** A result came in while you weren't on a call with them. */
  missedCall: boolean;
}

export interface ContactInputs {
  agents: Record<string, AgentState>;
  bang: Record<string, string[]>;
  ringing: Record<string, boolean>;
  board: Board | null;
  /** The role you're on a call with (connecting or live). */
  onLine: string | null;
}

const firstNameOf = (name: string) => name.split(" ")[0] || name;

/** Contacts sorted by first name, like a phone. */
export function buildContacts(roles: Role[], s: ContactInputs): Contact[] {
  return roles
    .map((r): Contact => {
      const tasks = s.board?.columns.in_progress.filter((c) => c.assignee_role === r.id) ?? [];
      let status: ContactStatus = "idle";
      if (s.onLine === r.id) status = "on_call";
      else if (s.agents[r.id] === "on_call") status = "busy"; // on a call somewhere else
      else if (s.agents[r.id] === "working" || tasks.length > 0) status = "working";

      let statusText = "Available";
      if (status === "on_call") statusText = "On a call with you";
      else if (status === "busy") statusText = "On another call";
      else if (status === "working") {
        statusText = tasks.length ? `Working on: ${tasks[0].title}` : "Working";
        if (tasks.length > 1) statusText += ` (+${tasks.length - 1} more)`;
      }

      return {
        roleId: r.id,
        name: r.name,
        firstName: firstNameOf(r.name),
        title: r.title,
        status,
        statusText,
        unseen: s.bang[r.id] ?? [],
        missedCall: s.ringing[r.id] === true,
      };
    })
    .sort((a, b) => a.firstName.localeCompare(b.firstName));
}

/** Arrow-key movement through the list: clamped, no wrap-around. */
export function moveSelection(index: number, delta: number, count: number): number {
  if (count <= 0) return 0;
  return Math.min(count - 1, Math.max(0, index + delta));
}
