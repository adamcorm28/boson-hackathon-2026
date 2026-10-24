import { useEffect, useState } from "react";
import { gateway } from "./api";
import type { Role } from "./api/types";
import { CallWindow } from "./call/CallWindow";
import { useCall } from "./call/useCall";
import { DevPanel } from "./dev/DevPanel";
import { Office } from "./office/Office";

// The gateway test panel lives at ?dev
export default function App() {
  return new URLSearchParams(location.search).has("dev") ? <DevPanel /> : <OfficeApp />;
}

function OfficeApp() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [boardOpen, setBoardOpen] = useState(false);
  const call = useCall(gateway);
  const onLine = call.state.status === "connecting" || call.state.status === "live" ? call.state.roleId : null;

  useEffect(() => {
    const loadRoles = () =>
      gateway.fetchRoles().then(
        (r) => {
          setRoles(r);
          setError(null);
        },
        (e: unknown) => setError(String(e)),
      );
    loadRoles();
    return gateway.subscribe((e) => {
      if (e.type === "resync") loadRoles();
    });
  }, []);

  // Temporary board overlay until the whiteboard lands (C7): B or Esc closes it.
  useEffect(() => {
    if (!boardOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key.toLowerCase() === "b") setBoardOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [boardOpen]);

  return (
    <main className="app">
      <header className="title">
        <h1>DUNDER MIFFLIN · SCRANTON</h1>
        <span className="muted">Infinity Voice™</span>
      </header>
      {error && <p className="error">Can't reach the gateway: {error}</p>}

      <Office
        roles={roles}
        activeRoleId={onLine}
        onDial={call.dial}
        onHangup={call.hangup}
        onOpenBoard={() => setBoardOpen(true)}
        paused={boardOpen}
      />

      {boardOpen && (
        <div className="overlay">
          <div className="overlay-card">
            <h2>Whiteboard</h2>
            <p className="muted">The Kanban board arrives in C7. Press B or Esc to close.</p>
          </div>
        </div>
      )}

      <CallWindow state={call.state} roles={roles} talking={call.talking} onHangup={call.hangup} onRetryMic={call.retryMic} />
    </main>
  );
}
