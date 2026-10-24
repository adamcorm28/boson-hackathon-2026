// Classic mode: a phone contact list instead of the walkable office.
// Click a name to call, or ↑/↓ (W/S) to pick and Enter (E) to call. B opens the whiteboard.
import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentState, Board, Role } from "../api/types";
import { Portrait } from "../call/Portrait";
import { buildContacts, moveSelection } from "./contacts";

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

function useClock(): string {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(t);
  }, []);
  return now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
  const clock = useClock();
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

  return (
    <div className="classic-phone" aria-label="Contacts">
      <div className="phone-screen">
        <div className="phone-status">
          <span>DUNDER MOBILE</span>
          <span className="phone-notch" aria-hidden />
          <span>
            {clock} <span className="phone-battery" aria-hidden />
          </span>
        </div>

        <header className="phone-head">
          <h2>Contacts</h2>
          <span>Scranton Branch</span>
        </header>

        {contacts.length === 0 && <p className="phone-empty">Loading the team…</p>}
        <ul className="contacts" role="listbox" aria-label="Employees">
          {contacts.map((c, i) => {
            const avatar = avatarOf(c.roleId);
            return (
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
                  {avatar ? <img src={avatar} alt="" /> : <Portrait roleId={c.roleId} talking={c.status === "on_call"} pixel={3} />}
                  <span className={`contact-dot ${c.status}`} aria-hidden />
                </span>
                <span className="contact-text">
                  <span className="contact-name">{c.name}</span>
                  <span className="contact-title">{c.title}</span>
                  <span className={`contact-status ${c.status}`}>{c.statusText}</span>
                </span>
                <span className="contact-side">
                  {c.missedCall && (
                    <span className="contact-missed" title="Missed call: they finished something while you were away">
                      ☎ missed
                    </span>
                  )}
                  {c.unseen.length > 0 && (
                    <button
                      className="contact-bang"
                      title="Open the finished result"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenResult(c.unseen[0]);
                      }}
                    >
                      ! {c.unseen.length > 1 ? c.unseen.length : "result"}
                    </button>
                  )}
                  <span className="contact-call" aria-hidden>
                    📞
                  </span>
                </span>
              </li>
            );
          })}
        </ul>

        <footer className="phone-keys">
          <kbd>↑↓</kbd> select <kbd>Enter</kbd> call <kbd>Esc</kbd> hang up <kbd>B</kbd> board <kbd>M</kbd> arcade
        </footer>
      </div>
    </div>
  );
}
