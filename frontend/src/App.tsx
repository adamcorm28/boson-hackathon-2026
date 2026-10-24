import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { gateway, USE_MOCK } from "./api";
import type { Board, Role } from "./api/types";
import { boardReducer } from "./board/boardReducer";
import { Whiteboard } from "./board/Whiteboard";
import { CallChooser } from "./call/CallChooser";
import { CallWindow } from "./call/CallWindow";
import { useCall } from "./call/useCall";
import { ContactList } from "./contacts/ContactList";
import { DevPanel } from "./dev/DevPanel";
import { loadStoredMode, otherMode, pickMode, storeMode, type Mode } from "./modes";
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
  const [mode, setMode] = useState<Mode>(() => pickMode(location.search, loadStoredMode()));
  const [office, officeDispatch] = useReducer(officeReducer, undefined, () => initialOfficeState());
  const call = useCall(gateway);
  const onLine = call.state.status === "connecting" || call.state.status === "live" ? call.state.roleId : null;
  // Walking up to a desk (or picking a contact) asks audio or video first; the choice starts the call.
  const [choosingFor, setChoosingFor] = useState<string | null>(null);
  const overlayOpen = titleOpen || boardOpen || resultTaskId !== null || choosingFor !== null;

  useEffect(() => storeMode(mode), [mode]);
  // The page background and overlays follow the mode's theme too.
  useEffect(() => {
    document.body.dataset.theme = mode;
  }, [mode]);

  // M switches between arcade and classic (not mid-call or behind an overlay).
  const canSwitch = !overlayOpen && call.state.status === "idle";
  useEffect(() => {
    if (!canSwitch) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "m" && !e.repeat && !e.metaKey && !e.ctrlKey && !e.altKey) setMode(otherMode);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canSwitch]);

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

  const dial = useCallback((roleId: string) => setChoosingFor(roleId), []);
  const startCall = useCallback(
    (roleId: string, video: boolean) => {
      setChoosingFor(null);
      officeDispatch({ type: "called", roleId }); // calling them clears their "!" and ringing phone
      call.dial(roleId, video);
    },
    [call.dial],
  );
  const choosingRole = roles.find((r) => r.id === choosingFor) ?? null;

  const openResult = useCallback((taskId: string) => {
    officeDispatch({ type: "opened_result", task_id: taskId });
    setResultTaskId(taskId);
  }, []);
  const dismissToast = useCallback((id: string) => officeDispatch({ type: "dismiss_toast", id }), []);

  return (
    <main className={`app theme-${mode}`}>
      <header className="title">
        {mode === "arcade" ? (
          <>
            <h1>DUNDER MIFFLIN · SCRANTON</h1>
            <span className="muted">Infinity Voice™</span>
          </>
        ) : (
          <>
            <h1>Dunder Mifflin</h1>
            <span className="muted">Scranton Branch · Infinity Voice</span>
          </>
        )}
        <div className="mode-switch" role="radiogroup" aria-label="Mode">
          {(["arcade", "classic"] as const).map((m) => (
            <button
              key={m}
              role="radio"
              aria-checked={mode === m}
              className={mode === m ? "selected" : ""}
              disabled={!canSwitch && mode !== m}
              onClick={() => setMode(m)}
              title={m === "arcade" ? "Walk the office (M)" : "Phone contact list (M)"}
            >
              {m === "arcade" ? "ARCADE" : "CLASSIC"}
            </button>
          ))}
        </div>
      </header>
      {error && <p className="error">Can't reach the gateway: {error}</p>}

      <div className={`stage ${mode}`}>
        {mode === "arcade" ? (
          <Office
            roles={roles}
            activeRoleId={onLine}
            onDial={dial}
            onHangup={call.hangup}
            onOpenBoard={() => setBoardOpen(true)}
            paused={overlayOpen}
            agents={agents}
            bang={office.bang}
            ringing={office.ringing}
          />
        ) : (
          <ContactList
            roles={roles}
            board={board}
            agents={agents}
            bang={office.bang}
            ringing={office.ringing}
            onLine={onLine}
            paused={overlayOpen || call.state.status !== "idle"}
            onDial={dial}
            onOpenBoard={() => setBoardOpen(true)}
            onOpenResult={openResult}
          />
        )}
        <Hud
          board={board}
          roles={roles}
          justMoved={justMoved}
          toasts={office.toasts}
          onOpenBoard={() => setBoardOpen(true)}
          onOpenResult={openResult}
          onDismissToast={dismissToast}
          variant={mode}
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

      {choosingRole && (
        <CallChooser
          role={choosingRole}
          onChoose={(video) => startCall(choosingRole.id, video)}
          onCancel={() => setChoosingFor(null)}
          classic={mode === "classic"}
        />
      )}

      {resultTaskId && (
        <ResultViewer gateway={gateway} roles={roles} taskId={resultTaskId} onClose={() => setResultTaskId(null)} />
      )}

      {titleOpen && <TitleCard mode={mode} onModeChange={setMode} mock={USE_MOCK} onStart={() => setTitleOpen(false)} />}

      <CallWindow state={call.state} roles={roles} talking={call.talking} media={call.media} muted={call.muted} onToggleMute={call.toggleMute} onHangup={call.hangup} onRetryMic={call.retryMic} classic={mode === "classic"} />
    </main>
  );
}
