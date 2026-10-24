// Basic result viewer: the RESULT summary and artifact links. C7 adds the CRT frame and the diff view.
import { useEffect, useState } from "react";
import type { Gateway, TaskDetail } from "../api/types";
import { useOverlayKeys } from "../ui/useOverlayKeys";

export function ResultViewer({ gateway, taskId, onClose }: { gateway: Gateway; taskId: string; onClose(): void }) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useOverlayKeys(true, onClose);

  useEffect(() => {
    setTask(null);
    setError(null);
    gateway.fetchTask(taskId).then(setTask, (e: unknown) => setError(String(e)));
  }, [gateway, taskId]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="overlay-card result" onClick={(e) => e.stopPropagation()}>
        <h2>{task ? task.title : taskId}</h2>
        {error && <p className="error">Couldn't load the result: {error}</p>}
        {!task && !error && <p className="muted">Loading…</p>}
        {task && (
          <>
            <p>{task.result_summary ?? "No result yet."}</p>
            <ul>
              {task.artifacts.map((a) => (
                <li key={a.url}>
                  <a href={a.url} target="_blank" rel="noreferrer">
                    {a.label}
                  </a>{" "}
                  <span className="muted">({a.kind})</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <button onClick={onClose}>
          Close <kbd>Esc</kbd>
        </button>
      </div>
    </div>
  );
}
