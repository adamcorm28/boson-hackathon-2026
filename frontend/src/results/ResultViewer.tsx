// The result, framed as a CRT monitor: RESULT summary, then each artifact
// (diff rendered inline, PR/link to open, pptx/xlsx to download).
import { useEffect, useState } from "react";
import type { Artifact, Gateway, Role, TaskDetail } from "../api/types";
import { useOverlayKeys } from "../ui/useOverlayKeys";
import { diffLineKind } from "./diff";

function DiffView({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(
        (t) => !cancelled && setText(t),
        (e: unknown) => !cancelled && setError(String(e)),
      );
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (error) return <p className="error">Couldn't load the diff: {error}</p>;
  if (text === null) return <p className="muted">Loading diff…</p>;
  return (
    <pre className="diff">
      {text.split("\n").map((line, i) => (
        <div key={i} className={diffLineKind(line)}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

function ArtifactView({ a }: { a: Artifact }) {
  switch (a.kind) {
    case "diff":
      return (
        <div className="artifact">
          <div className="artifact-label">📄 {a.label}</div>
          <DiffView url={a.url} />
        </div>
      );
    case "pr":
    case "link":
      return (
        <div className="artifact">
          <a className="artifact-button" href={a.url} target="_blank" rel="noreferrer">
            {a.kind === "pr" ? "🔀 Open PR" : "🔗 Open"}: {a.label}
          </a>
        </div>
      );
    case "pdf":
      return (
        <div className="artifact">
          <a className="artifact-button" href={a.url} target="_blank" rel="noreferrer">
            📕 Open PDF: {a.label}
          </a>
          <iframe className="pdf-frame" src={a.url} title={a.label} />
        </div>
      );
    case "pptx":
    case "xlsx":
      return (
        <div className="artifact">
          <a className="artifact-button" href={a.url} download>
            ⬇ Download {a.kind === "pptx" ? "deck" : "spreadsheet"}: {a.label}
          </a>
        </div>
      );
    default:
      return null;
  }
}

interface Props {
  gateway: Gateway;
  roles: Role[];
  taskId: string;
  onClose(): void;
}

export function ResultViewer({ gateway, roles, taskId, onClose }: Props) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useOverlayKeys(true, onClose);

  useEffect(() => {
    let cancelled = false;
    setTask(null);
    setError(null);
    gateway.fetchTask(taskId).then(
      (t) => !cancelled && setTask(t),
      (e: unknown) => !cancelled && setError(String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [gateway, taskId]);

  const who = roles.find((r) => r.id === task?.assignee_role)?.name;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="crt" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Task result">
        <div className="crt-screen">
          <div className="crt-head">
            <span>
              {taskId} · {task?.status.replace("_", " ").toUpperCase() ?? "…"}
            </span>
            <button onClick={onClose}>
              Close <kbd>Esc</kbd>
            </button>
          </div>
          {error && <p className="error">Couldn't load the result: {error}</p>}
          {!task && !error && <p className="muted">Loading…</p>}
          {task && (
            <>
              <h2 className="crt-title">{task.title}</h2>
              {who && <p className="muted">by {who}</p>}
              <p className="crt-summary">{task.result_summary ?? "No result yet: still being worked on."}</p>
              {task.artifacts.map((a) => (
                <ArtifactView key={a.url} a={a} />
              ))}
            </>
          )}
        </div>
        <div className="crt-base">DUNDER MIFFLIN INFINITY</div>
      </div>
    </div>
  );
}
