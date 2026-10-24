import { useEffect, useState } from "react";
import { gateway, GATEWAY_URL, USE_MOCK } from "./api";
import type { Role, ServerEvent } from "./api/types";

// Temporary connection check: lists /roles and the latest /events.
// Replaced by the office (C5) and call window (C4).
export default function App() {
  const [roles, setRoles] = useState<Role[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<ServerEvent[]>([]);

  useEffect(() => {
    const load = () =>
      gateway.fetchRoles().then(
        (r) => {
          setRoles(r);
          setError(null);
        },
        (e: unknown) => setError(String(e)),
      );
    load();
    return gateway.subscribe((e) => {
      if (e.type === "resync") load();
      setEvents((prev) => [e, ...prev].slice(0, 10));
    });
  }, []);

  return (
    <main className="app">
      <h1>Dunder Mifflin Infinity Voice™</h1>
      <p className="muted">Gateway: {USE_MOCK ? "mock (VITE_MOCK=1)" : GATEWAY_URL}</p>

      <h2>Roles</h2>
      {error && <p className="error">Can't reach the gateway: {error}</p>}
      {roles && (
        <ul>
          {roles.map((r) => (
            <li key={r.id}>
              {r.name}: {r.title} ({r.id}, desk {r.desk ?? "auto"})
            </li>
          ))}
        </ul>
      )}

      <h2>Live events</h2>
      {events.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <ul className="events">
          {events.map((e, i) => (
            <li key={i}>
              <code>{JSON.stringify(e)}</code>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
