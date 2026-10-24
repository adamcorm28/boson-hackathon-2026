// The selected contact's profile: who they are, what they're responsible for, what they're doing,
// how it's going, and their tasks. One click on "Call" (or Enter) rings them.
import { useEffect, useMemo, useState } from "react";
import { BOARD_COLUMNS, type AgentStatusDetail, type Board, type BoardColumn, type Gateway, type Role } from "../api/types";
import { Avatar } from "../ui/Avatar";
import { PhoneIcon, PRESENCE } from "./ContactList";
import type { Contact } from "./contacts";
import { buildProfile } from "./profile";

interface Props {
  gateway: Gateway;
  role: Role;
  roles: Role[];
  board: Board | null;
  contact: Contact;
  onDial(roleId: string): void;
  onOpenResult(taskId: string): void;
}

const COLUMN_LABEL: Record<BoardColumn, string> = {
  backlog: "Backlog",
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  done: "Done",
};
const POLL_MS = 10_000; // progress notes don't arrive as events, so check in while they're working
const MAX_OPEN = 6;

/** Their latest progress note, refreshed when their work changes and every few seconds while working. */
function useAgentStatus(gateway: Gateway, roleId: string, refreshKey: string, working: boolean) {
  const [status, setStatus] = useState<AgentStatusDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setStatus(null);
    setLoading(true);
  }, [roleId]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      gateway.fetchAgentStatus(roleId).then(
        (s) => {
          if (!cancelled) {
            setStatus(s);
            setLoading(false);
          }
        },
        () => {
          if (!cancelled) setLoading(false); // no status route or company down: just don't show a note
        },
      );
    load();
    const t = working ? setInterval(load, POLL_MS) : null;
    return () => {
      cancelled = true;
      if (t) clearInterval(t);
    };
  }, [gateway, roleId, refreshKey, working]);

  return { status, loading };
}

export function ContactProfile({ gateway, role, roles, board, contact, onDial, onOpenResult }: Props) {
  const profile = useMemo(() => buildProfile(role, roles, board, contact), [role, roles, board, contact]);
  const working = contact.status === "working" || profile.counts.in_progress > 0;
  const refreshKey = profile.open.map((c) => `${c.task_id}:${c.status}`).join(",");
  const { status, loading } = useAgentStatus(gateway, role.id, refreshKey, working);
  const noteTask = board && status?.current_task_id
    ? BOARD_COLUMNS.flatMap((col) => board.columns[col]).find((c) => c.task_id === status.current_task_id)
    : undefined;

  return (
    <section className="profile-card" aria-label={`${role.name}'s profile`}>
      <header className="profile-head">
        <Avatar roleId={role.id} name={role.name} src={role.avatar_url} size={72} />
        <div className="profile-id">
          <h2>{role.name}</h2>
          <p className="profile-title">{role.title}</p>
          <span className={`profile-presence ${contact.status}`}>
            <span className={`presence-dot ${contact.status}`} /> {PRESENCE[contact.status]}
          </span>
        </div>
      </header>

      <div className="profile-org">
        {profile.manager ? (
          <span>
            Reports to <b>{profile.manager.name}</b>
          </span>
        ) : (
          <span>Leads the branch</span>
        )}
        {profile.reports.length > 0 && (
          <span>
            Manages <b>{profile.reports.map((r) => r.name).join(", ")}</b>
          </span>
        )}
      </div>

      <button className="profile-call" onClick={() => onDial(role.id)} disabled={contact.status === "on_call"}>
        <PhoneIcon size={16} /> {contact.status === "on_call" ? "On a call" : `Call ${contact.firstName}`}
        <kbd>Enter</kbd>
      </button>

      <div className="profile-body">
        {profile.responsibilities.length > 0 && (
          <section>
            <h3>Responsibilities</h3>
            <ul className="profile-list">
              {profile.responsibilities.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3>What they're doing</h3>
          <p className={`profile-now ${contact.status}`}>{profile.now}</p>
          {status?.last_comment ? (
            <blockquote className="profile-note">
              <span className="profile-note-label">Latest update{noteTask ? ` · ${noteTask.title}` : ""}</span>
              {status.last_comment}
            </blockquote>
          ) : (
            working && loading && <p className="profile-muted">Checking in…</p>
          )}
        </section>

        <section>
          <h3>How it's going</h3>
          <ul className="profile-progress">
            {profile.progress.map((h) => (
              <li key={h.text} className={h.tone}>
                {h.text}
              </li>
            ))}
          </ul>
          <div className="profile-counts">
            {BOARD_COLUMNS.filter((col) => profile.counts[col] > 0).map((col) => (
              <span key={col} className={`count ${col}`}>
                {COLUMN_LABEL[col]} <b>{profile.counts[col]}</b>
              </span>
            ))}
          </div>
        </section>

        {(profile.open.length > 0 || profile.done.length > 0) && (
          <section>
            <h3>Their tasks</h3>
            <ul className="profile-tasks">
              {profile.open.slice(0, MAX_OPEN).map((c) => (
                <li key={c.task_id}>
                  <button onClick={() => onOpenResult(c.task_id)} title="Open the task">
                    <span className={`task-status ${c.status}`}>{COLUMN_LABEL[c.status as BoardColumn] ?? c.status}</span>
                    <span className="task-title">{c.title}</span>
                  </button>
                </li>
              ))}
              {profile.done.slice(0, 3).map((c) => (
                <li key={c.task_id}>
                  <button onClick={() => onOpenResult(c.task_id)} title="Open the result">
                    <span className="task-status done">Done</span>
                    <span className="task-title">{c.title}</span>
                  </button>
                </li>
              ))}
            </ul>
            {profile.open.length > MAX_OPEN && (
              <p className="profile-muted">+{profile.open.length - MAX_OPEN} more on the task board</p>
            )}
          </section>
        )}
      </div>
    </section>
  );
}
