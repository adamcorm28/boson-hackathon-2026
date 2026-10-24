// Classic mode's main area: the contact list and the selected person's profile, side by side.
import { useMemo, useState } from "react";
import type { AgentState, Board, Gateway, Role } from "../api/types";
import { ContactList } from "./ContactList";
import { ContactProfile } from "./ContactProfile";
import { buildContacts } from "./contacts";

interface Props {
  gateway: Gateway;
  roles: Role[];
  board: Board | null;
  agents: Record<string, AgentState>;
  bang: Record<string, string[]>;
  ringing: Record<string, boolean>;
  onLine: string | null;
  paused: boolean;
  onDial(roleId: string): void;
  onOpenBoard(): void;
  onOpenResult(taskId: string): void;
}

export function ClassicView({ gateway, roles, board, agents, bang, ringing, onLine, paused, onDial, onOpenBoard, onOpenResult }: Props) {
  const contacts = useMemo(
    () => buildContacts(roles, { agents, bang, ringing, board, onLine }),
    [roles, agents, bang, ringing, board, onLine],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = contacts.find((c) => c.roleId === selectedId) ?? contacts[0];
  const selectedRole = selected ? roles.find((r) => r.id === selected.roleId) : undefined;

  return (
    <>
      <ContactList
        roles={roles}
        contacts={contacts}
        selectedId={selected?.roleId ?? null}
        onSelect={setSelectedId}
        paused={paused}
        onDial={onDial}
        onOpenBoard={onOpenBoard}
        onOpenResult={onOpenResult}
      />
      {selected && selectedRole && (
        <ContactProfile
          gateway={gateway}
          role={selectedRole}
          roles={roles}
          board={board}
          contact={selected}
          onDial={onDial}
          onOpenResult={onOpenResult}
        />
      )}
    </>
  );
}
