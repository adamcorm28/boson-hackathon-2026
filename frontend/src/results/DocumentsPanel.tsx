// Side panel listing every finished task that produced files (reports, decks, spreadsheets, fixes).
// Open it with F or the header button; clicking an entry opens it in the result viewer.
import { useEffect, useState } from "react";
import type { DocumentEntry, Gateway, Role } from "../api/types";

const ICON: Record<string, string> = { pdf: "📕", pptx: "📊", xlsx: "📈", diff: "📄", pr: "🔀", link: "📄" };

interface Props {
  gateway: Gateway;
  roles: Role[];
  /** Bumped when a task completes, so the list refreshes. */
  version: number;
  onOpen(taskId: string): void;
  onClose(): void;
}

export function DocumentsPanel({ gateway, roles, version, onOpen, onClose }: Props) {
  const [docs, setDocs] = useState<DocumentEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    gateway.fetchDocuments().then(
      (d) => !cancelled && (setDocs(d), setError(null)),
      (e: unknown) => !cancelled && setError(String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [gateway, version]);

  const who = (roleId: string | null) => roles.find((r) => r.id === roleId)?.name ?? roleId ?? "Someone";

  return (
    <aside className="docs-panel" aria-label="Documents">
      <div className="docs-head">
        <h2>Documents</h2>
        <button onClick={onClose}>
          Close <kbd>F</kbd>
        </button>
      </div>
      {error && <p className="error">Couldn't load documents: {error}</p>}
      {!docs && !error && <p className="muted">Loading…</p>}
      {docs && docs.length === 0 && <p className="muted">Nothing yet. Ask someone for a report.</p>}
      {docs?.map((d) => (
        <button key={d.task_id} className="docs-item" onClick={() => onOpen(d.task_id)}>
          <span className="docs-title">
            {d.artifacts.map((a) => ICON[a.kind] ?? "📄").join(" ")} {d.title}
          </span>
          <span className="muted">{who(d.from_role)}</span>
          <span className="docs-summary">{d.summary}</span>
        </button>
      ))}
    </aside>
  );
}
