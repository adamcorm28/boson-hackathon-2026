// Live office state from SSE: who's busy, who has a finished result for you ("!"), whose phone rings, toasts.
import type { AgentState, Role, ServerEvent } from "../api/types";

export interface Toast {
  id: string;
  text: string;
  task_id: string;
}

export interface OfficeState {
  agents: Record<string, AgentState>;
  /** roleId -> task ids with results you haven't opened. */
  bang: Record<string, string[]>;
  /** A result arrived while you weren't on a call with them. */
  ringing: Record<string, boolean>;
  toasts: Toast[];
  /** roleId -> first name, for toast text. */
  names: Record<string, string>;
}

export type OfficeAction =
  | ServerEvent
  | { type: "opened_result"; task_id: string }
  | { type: "called"; roleId: string }
  | { type: "roles"; roles: Role[] }
  | { type: "dismiss_toast"; id: string };

const namesOf = (roles: Role[]) => Object.fromEntries(roles.map((r) => [r.id, r.name.split(" ")[0]]));

export function initialOfficeState(roles: Role[] = []): OfficeState {
  return { agents: {}, bang: {}, ringing: {}, toasts: [], names: namesOf(roles) };
}

function without<T>(rec: Record<string, T>, key: string): Record<string, T> {
  if (!(key in rec)) return rec;
  const copy = { ...rec };
  delete copy[key];
  return copy;
}

export function officeReducer(state: OfficeState, action: OfficeAction): OfficeState {
  switch (action.type) {
    case "agent.status":
      return state.agents[action.role] === action.state ? state : { ...state, agents: { ...state.agents, [action.role]: action.state } };

    case "task.completed": {
      const ids = state.bang[action.from_role] ?? [];
      if (ids.includes(action.task_id)) return state;
      const name = (state.names[action.from_role] ?? action.from_role).toUpperCase();
      return {
        ...state,
        bang: { ...state.bang, [action.from_role]: [...ids, action.task_id] },
        toasts: [...state.toasts, { id: action.task_id, text: `${name}: ${action.title} is done!`, task_id: action.task_id }],
      };
    }

    case "ping":
      // A ping with a to_role was announced inside that call; only "nobody was on the line" rings.
      if (action.to_role !== null || state.ringing[action.from_role]) return state;
      return { ...state, ringing: { ...state.ringing, [action.from_role]: true } };

    case "called": {
      if (!(action.roleId in state.bang) && !(action.roleId in state.ringing)) return state;
      return { ...state, bang: without(state.bang, action.roleId), ringing: without(state.ringing, action.roleId) };
    }

    case "opened_result": {
      let bang = state.bang;
      let ringing = state.ringing;
      for (const [roleId, ids] of Object.entries(state.bang)) {
        if (!ids.includes(action.task_id)) continue;
        const left = ids.filter((id) => id !== action.task_id);
        bang = left.length ? { ...bang, [roleId]: left } : without(bang, roleId);
        if (!left.length) ringing = without(ringing, roleId);
      }
      return { ...state, bang, ringing, toasts: state.toasts.filter((t) => t.task_id !== action.task_id) };
    }

    case "dismiss_toast":
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) };

    case "roles":
      return { ...state, names: namesOf(action.roles) };

    default:
      return state; // task.updated / resync are the board's business
  }
}
