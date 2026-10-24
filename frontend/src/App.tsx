import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { gateway, USE_MOCK } from "./api";
import type { Board, Role } from "./api/types";
import { boardReducer } from "./board/boardReducer";
import { Whiteboard } from "./board/Whiteboard";
import { CallWindow } from "./call/CallWindow";
import { useCall } from "./call/useCall";
import { DevPanel } from "./dev/DevPanel";
import { Hud } from "./office/Hud";
import { Office } from "./office/Office";
import { initialOfficeState, officeReducer } from "./office/officeReducer";
import { ResultViewer } from "./results/ResultViewer";
import { TitleCard } from "./ui/TitleCard";

const MOVED_HIGHLIGHT_MS = 2500;

// The gateway test panel lives at ?dev
export default function App() {
  return new URLSearchParams(location.search).has("dev") ? <DevPanel /> : <OfficeApp />;
}

function OfficeApp() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [board, setBoard] = useState<Board | null>(null);
  const [justMoved, setJustMoved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [boardOpen, setBoardOpen] = useState(false);
  const [resultTaskId, setResultTaskId] = useState<string | null>(null);
  const [titleOpen, setTitleOpen] = useState(() => !new URLSearchParams(location.search).has("notitle"));
  const [office, officeDispatch] = useReducer(officeReducer, undefined, () => initialOfficeState());
  const call = useCall(gateway);
  const onLine = call.state.status === "connecting" || call.state.status === "live" ? call.state.roleId : null;

  useEffect(() => {
    const loadRoles = () =>
      gateway.fetchRoles().then(
        (r) => {
          setRoles(r);
          officeDispatch({ type: "roles", roles: r });
          setError(null);
        },
        (e: unknown) => setError(String(e)),
      );
    const loadBoard = () => gateway.fetchBoard().then(setBoard, () => {});
    loadRoles();
    loadBoard();
    return gateway.subscribe((e) => {
      officeDispatch(e);
      if (e.type === "task.updated") {
        setBoard((b) => (b ? boardReducer(b, e) : b));
        setJustMoved(e.task_id);
      }
      if (e.type === "resync") {
        loadRoles();
        loadBoard();
      }
    });
  }, []);

  useEffect(() => {
    if (!justMoved) return;
    const t = setTimeout(() => setJustMoved(null), MOVED_HIGHLIGHT_MS);
    return () => clearTimeout(t);
  }, [justMoved]);

  // A monitor glows when the agent has an in-progress card, even before any agent.status event
  // (e.g. work that was already running when the page loaded).
  const agents = useMemo(() => {
    const merged = { ...office.agents };
    for (const card of board?.columns.in_progress ?? []) {
      if (card.assignee_role && merged[card.assignee_role] !== "on_call") merged[card.assignee_role] = "working";
    }
    return merged;
  }, [office.agents, board]);

  const dial = useCallback(
    (roleId: string) => {
      officeDispatch({ type: "called", roleId }); // calling them clears their "!" and ringing phone
      call.dial(roleId);
    },
    [call.dial],
  );

  const openResult = useCallback((taskId: string) => {
    officeDispatch({ type: "opened_result", task_id: taskId });
    setResultTaskId(taskId);
  }, []);
  const dismissToast = useCallback((id: string) => officeDispatch({ type: "dismiss_toast", id }), []);

  return (
    <main className="app">
      <header className="title">
        <h1>DUNDER MIFFLIN · SCRANTON</h1>
        <span className="muted">Infinity Voice™</span>
      </header>
      {error && <p className="error">Can't reach the gateway: {error}</p>}

      <div className="stage">
        <Office
          roles={roles}
          activeRoleId={onLine}
          onDial={dial}
          onHangup={call.hangup}
          onOpenBoard={() => setBoardOpen(true)}
          paused={titleOpen || boardOpen || resultTaskId !== null}
          agents={agents}
          bang={office.bang}
          ringing={office.ringing}
        />
        <Hud
          board={board}
          roles={roles}
          toasts={office.toasts}
          onOpenBoard={() => setBoardOpen(true)}
          onOpenResult={openResult}
          onDismissToast={dismissToast}
        />
      </div>

      {boardOpen && (
        <Whiteboard
          board={board}
          roles={roles}
          justMoved={justMoved}
          onOpenCard={openResult}
          onClose={() => setBoardOpen(false)}
        />
      )}

      {resultTaskId && (
        <ResultViewer gateway={gateway} roles={roles} taskId={resultTaskId} onClose={() => setResultTaskId(null)} />
      )}

      {titleOpen && <TitleCard mock={USE_MOCK} onStart={() => setTitleOpen(false)} />}

      <CallWindow state={call.state} roles={roles} talking={call.talking} onHangup={call.hangup} onRetryMic={call.retryMic} />
    </main>
  );
}
