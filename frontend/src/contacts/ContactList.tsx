// Classic mode's contact list. Click someone (or ↑/↓) to see their profile; Enter, double-click or
// the phone button calls them. B opens the task board.
import { useEffect, useRef } from "react";
import type { Role } from "../api/types";
import { Avatar } from "../ui/Avatar";
import { moveSelection, type Contact, type ContactStatus } from "./contacts";

interface Props {
  roles: Role[];
  contacts: Contact[];
  selectedId: string | null;
  onSelect(roleId: string): void;
  /** Ignore the keyboard (title card, overlays or a call are open). */
  paused: boolean;
  onDial(roleId: string): void;
  onOpenBoard(): void;
  onOpenResult(taskId: string): void;
}

const UP = new Set(["ArrowUp", "w"]);
const DOWN = new Set(["ArrowDown", "s"]);
const CALL = new Set(["Enter", "e"]);

export const PRESENCE: Record<ContactStatus, string> = {
  idle: "Available",
  working: "Working",
  on_call: "On a call",
  busy: "On a call",
};

export function PhoneIcon({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <path
        fill="currentColor"
        d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"
      />
    </svg>
  );
}

export function ContactList({ roles, contacts, selectedId, onSelect, paused, onDial, onOpenBoard, onOpenResult }: Props) {
  const found = contacts.findIndex((c) => c.roleId === selectedId);
  const index = found >= 0 ? found : 0;
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const avatarOf = (id: string) => roles.find((r) => r.id === id)?.avatar_url ?? null;

  // Latest values for the key handler, which is registered once.
  const live = useRef({ contacts, index, paused, onDial, onOpenBoard, onSelect });
  live.current = { contacts, index, paused, onDial, onOpenBoard, onSelect };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { contacts, index, paused, onDial, onOpenBoard, onSelect } = live.current;
      if (paused || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (UP.has(key) || DOWN.has(key)) {
        e.preventDefault();
        const next = moveSelection(index, UP.has(key) ? -1 : 1, contacts.length);
        if (contacts[next]) onSelect(contacts[next].roleId);
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
            onClick={() => onSelect(c.roleId)}
            onDoubleClick={() => onDial(c.roleId)}
            title={`${c.firstName}'s profile (double-click to call)`}
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
              <button
                className="contact-call"
                title={`Call ${c.firstName}`}
                aria-label={`Call ${c.firstName}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onDial(c.roleId);
                }}
              >
                <PhoneIcon />
              </button>
            </span>
          </li>
        ))}
      </ul>

      <footer className="contacts-keys">
        <kbd>↑</kbd>
        <kbd>↓</kbd> select · <kbd>Enter</kbd> call · <kbd>B</kbd> board · <kbd>M</kbd> arcade
      </footer>
    </section>
  );
}
