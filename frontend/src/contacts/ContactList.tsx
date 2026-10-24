// Classic mode: a contact list instead of the walkable office.
// Click someone to call, or ↑/↓ (W/S) to pick and Enter (E) to call. B opens the task board.
import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentState, Board, Role } from "../api/types";
import { Avatar } from "../ui/Avatar";
import { buildContacts, moveSelection, type ContactStatus } from "./contacts";

interface Props {
  roles: Role[];
  board: Board | null;
  agents: Record<string, AgentState>;
  bang: Record<string, string[]>;
  ringing: Record<string, boolean>;
  /** The role on the line, while a call is connecting or live. */
  onLine: string | null;
  /** Ignore the keyboard (title card, overlays or a call are open). */
  paused: boolean;
  onDial(roleId: string): void;
  onOpenBoard(): void;
  onOpenResult(taskId: string): void;
}

const UP = new Set(["ArrowUp", "w"]);
const DOWN = new Set(["ArrowDown", "s"]);
const CALL = new Set(["Enter", "e"]);

const PRESENCE: Record<ContactStatus, string> = {
  idle: "Available",
  working: "Working",
  on_call: "On a call",
  busy: "On a call",
};

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <path
        fill="currentColor"
        d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"
      />
    </svg>
  );
}

export function ContactList({ roles, board, agents, bang, ringing, onLine, paused, onDial, onOpenBoard, onOpenResult }: Props) {
  const contacts = useMemo(
    () => buildContacts(roles, { agents, bang, ringing, board, onLine }),
    [roles, agents, bang, ringing, board, onLine],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const found = contacts.findIndex((c) => c.roleId === selectedId);
  const index = found >= 0 ? found : 0;
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const avatarOf = (id: string) => roles.find((r) => r.id === id)?.avatar_url ?? null;

  // Latest values for the key handler, which is registered once.
  const live = useRef({ contacts, index, paused, onDial, onOpenBoard });
  live.current = { contacts, index, paused, onDial, onOpenBoard };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { contacts, index, paused, onDial, onOpenBoard } = live.current;
      if (paused || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (UP.has(key) || DOWN.has(key)) {
        e.preventDefault();
        const next = moveSelection(index, UP.has(key) ? -1 : 1, contacts.length);
        if (contacts[next]) setSelectedId(contacts[next].roleId);
      } else if (CALL.has(key) && !e.repeat) {
        e.preventDefault();
        if (contacts[index]) onDial(contacts[index].roleId);
      } else if (key === "b" && !e.repeat) {
        onOpenBoard();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Keep the selected row in view when moving with the keyboard.
  const selected = contacts[index];
  useEffect(() => {
    if (selected) rowRefs.current.get(selected.roleId)?.scrollIntoView({ block: "nearest" });
  }, [selected?.roleId]);

  const available = contacts.filter((c) => c.status === "idle").length;

  return (
    <section className="contacts-card" aria-label="Contacts">
      <header className="contacts-head">
        <div>
          <h2>Contacts</h2>
          <p>
            Scranton Branch · {contacts.length} people · {available} available
          </p>
        </div>
      </header>

      {contacts.length === 0 && <p className="contacts-empty">Loading the team…</p>}
      <ul className="contacts" role="listbox" aria-label="Employees">
        {contacts.map((c, i) => (
          <li
            key={c.roleId}
            ref={(el) => {
              if (el) rowRefs.current.set(c.roleId, el);
              else rowRefs.current.delete(c.roleId);
            }}
            role="option"
            aria-selected={i === index}
            className={`contact ${i === index ? "selected" : ""} ${c.status}`}
            onMouseEnter={() => setSelectedId(c.roleId)}
            onClick={() => onDial(c.roleId)}
            title={`Call ${c.firstName}`}
          >
            <span className="contact-face">
              <Avatar roleId={c.roleId} name={c.name} src={avatarOf(c.roleId)} size={44} />
              <span className={`presence ${c.status}`} title={PRESENCE[c.status]} />
            </span>
            <span className="contact-text">
              <span className="contact-name">{c.name}</span>
              <span className="contact-title">{c.title}</span>
              <span className={`contact-status ${c.status}`}>{c.statusText}</span>
            </span>
            <span className="contact-side">
              {c.missedCall && <span className="pill missed">Missed call</span>}
              {c.unseen.length > 0 && (
                <button
                  className="pill result"
                  title="Open the finished result"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenResult(c.unseen[0]);
                  }}
                >
                  {c.unseen.length > 1 ? `${c.unseen.length} results ready` : "Result ready"}
                </button>
              )}
              <span className="contact-call" aria-hidden>
                <PhoneIcon />
              </span>
            </span>
          </li>
        ))}
      </ul>

      <footer className="contacts-keys">
        <kbd>↑</kbd>
        <kbd>↓</kbd> select · <kbd>Enter</kbd> call · <kbd>Esc</kbd> hang up · <kbd>B</kbd> task board · <kbd>M</kbd> arcade
        mode
      </footer>
    </section>
  );
}
