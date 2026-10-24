// Arcade-style "DWIGHT: Fix bulk discount is done!" toasts. Click to open the result.
import { useEffect } from "react";
import type { Toast } from "../office/officeReducer";

const TOAST_MS = 12_000;

function ToastItem({ toast, onOpen, onDismiss }: { toast: Toast; onOpen(taskId: string): void; onDismiss(id: string): void }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(toast.id), TOAST_MS);
    return () => clearTimeout(t);
  }, [toast.id, onDismiss]);

  return (
    <div className="toast">
      <button className="toast-open" onClick={() => onOpen(toast.task_id)}>
        <span className="toast-bang">!</span> {toast.text}
        <span className="toast-cta">VIEW ▶</span>
      </button>
      <button className="toast-x" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>
        ×
      </button>
    </div>
  );
}

export function Toasts({ toasts, onOpen, onDismiss }: { toasts: Toast[]; onOpen(taskId: string): void; onDismiss(id: string): void }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onOpen={onOpen} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
