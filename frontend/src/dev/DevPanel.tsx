// Temporary test panel for the gateway (mock or real), until the office (C5) exists.
// Calls go through useCall + CallWindow, so the mic turns on automatically and Esc hangs up.
import { useEffect, useState } from "react";
import { gateway, GATEWAY_URL, USE_MOCK } from "../api";
import type { MockGateway } from "../api/mock";
import { BOARD_COLUMNS, CLOSE_ALREADY_ON_CALL, type AgentState, type Board, type Role, type TaskDetail } from "../api/types";
import { CallWindow } from "../call/CallWindow";
import { useCall } from "../call/useCall";

const mock = USE_MOCK ? (gateway as MockGateway) : null;
const FRAME_BYTES = 1920; // 40 ms of PCM16 24 kHz

interface LogLine {
  id: number;
  at: string;
  text: string;
}

let logId = 0;

export function DevPanel() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<Record<string, AgentState>>({});
  const [log, setLog] = useState<LogLine[]>([]);
  const [completed, setCompleted] = useState<string[]>([]);
  const [result, setResult] = useState<{ task: TaskDetail; diff: string | null } | null>(null);

  const addLog = (text: string) =>
    setLog((prev) => [{ id: logId++, at: new Date().toLocaleTimeString(), text }, ...prev].slice(0, 40));

  const call = useCall(gateway, {
    onEvent: (e) => {
      if (e.type !== "transcript.assistant.delta") addLog(`CALL ${JSON.stringify(e)}`);
    },
  });
  const live = call.state.status === "live";

  useEffect(() => {
    const loadRoles = () => gateway.fetchRoles().then(setRoles, (e: unknown) => setError(String(e)));
    const loadBoard = () => gateway.fetchBoard().then(setBoard, (e: unknown) => setError(String(e)));
    loadRoles();
    loadBoard();
    return gateway.subscribe((e) => {
      addLog(`SSE ${JSON.stringify(e)}`);
      if (e.type === "agent.status") setAgents((a) => ({ ...a, [e.role]: e.state }));
      if (e.type === "task.updated") loadBoard();
      if (e.type === "task.completed") setCompleted((ids) => (ids.includes(e.task_id) ? ids : [...ids, e.task_id]));
      if (e.type === "resync") {
        loadRoles();
        loadBoard();
      }
    });
  }, []);

  /** Opens a raw second socket to check the one-call-at-a-time rule without touching the current call. */
  function secondCall(role: Role) {
    const sock = gateway.openCall(role.id);
    sock.onClose((code) =>
      addLog(`second call to ${role.id} closed with ${code}${code === CLOSE_ALREADY_ON_CALL ? ' -> "Already on a call"' : ""}`),
    );
  }

  function talk(seconds: number) {
    const frames = Math.round((seconds * 1000) / 40);
    for (let i = 0; i < frames; i++) call.sendAudio(new ArrayBuffer(FRAME_BYTES));
  }

  async function openResult(taskId: string) {
    try {
      const task = await gateway.fetchTask(taskId);
      const diffArtifact = task.artifacts.find((a) => a.kind === "diff");
      const diff = diffArtifact ? await fetch(diffArtifact.url).then((r) => r.text()) : null;
      setResult({ task, diff });
    } catch (e) {
      addLog(`fetchTask(${taskId}) failed: ${String(e)}`);
    }
  }

  return (
    <main className="dev">
      <h1>Dunder Mifflin Infinity Voice™: gateway test panel</h1>
      <p className="muted">
        Gateway: {USE_MOCK ? "mock (VITE_MOCK=1)" : GATEWAY_URL}. Use headphones: otherwise the mic hears the speakers.
      </p>
      {USE_MOCK && (
        <ol className="muted steps">
          <li>Click Call next to anyone and allow the mic. You should hear the greeting.</li>
          <li>
            Say a short sentence, then pause: they delegate "Fix bulk discount" to Dwight and a card appears in todo.
            (No mic? Click "Talk 2 s".) Speak while they talk to interrupt: the audio should cut out at once.
          </li>
          <li>Watch the card move to in_progress, then done ~10 s later, with a ping and an announcement.</li>
          <li>Click "Open result" to see the summary and diff. Esc hangs up.</li>
        </ol>
      )}
      {error && <p className="error">Can't reach the gateway: {error}</p>}

      <div className="dev-row">
        <section className="dev-card">
          <h2>Roles</h2>
          <ul className="plain">
            {roles.map((r) => (
              <li key={r.id}>
                {call.state.status === "idle" ? (
                  <button onClick={() => call.dial(r.id)}>Call</button>
                ) : (
                  <button onClick={() => secondCall(r)} title="Should be rejected with 4409">
                    2nd call
                  </button>
                )}{" "}
                {r.name} <span className="muted">({r.id})</span>{" "}
                <span className={`badge ${agents[r.id] ?? "idle"}`}>{agents[r.id] ?? "idle"}</span>
              </li>
            ))}
          </ul>
          {mock && (
            <p>
              <button onClick={() => mock.resync()}>Simulate SSE reconnect</button>
            </p>
          )}
        </section>

        <section className="dev-card grow">
          <h2>Call test controls</h2>
          <p>
            <button disabled={!live} onClick={() => talk(2)}>Talk 2 s (silent)</button>{" "}
            <button disabled={!live} onClick={() => call.sendAudio(new Int16Array(FRAME_BYTES / 2).fill(12000).buffer)}>
              Interrupt (loud frame)
            </button>{" "}
            {mock && (
              <button disabled={!live} onClick={() => mock.endActiveCall("idle_timeout")}>
                End from server
              </button>
            )}
          </p>
          <p className="muted">Call status: {call.state.status}{call.talking ? " · agent talking" : ""}</p>
        </section>
      </div>

      <section className="dev-card">
        <h2>Board</h2>
        <div className="board">
          {BOARD_COLUMNS.map((col) => (
            <div key={col} className="column">
              <h3>{col}</h3>
              {board?.columns[col].map((card) => (
                <div key={card.task_id} className={`card ${card.origin}`}>
                  <b>{card.task_id}</b> {card.title} <span className="muted">({card.assignee_role ?? "unassigned"})</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>

      <div className="dev-row">
        <section className="dev-card">
          <h2>Finished results</h2>
          {completed.length === 0 && <p className="muted">None yet.</p>}
          {completed.map((id) => (
            <button key={id} onClick={() => openResult(id)}>
              Open result {id}
            </button>
          ))}
          {result && (
            <div>
              <h3>
                {result.task.task_id}: {result.task.title}
              </h3>
              <p>{result.task.result_summary}</p>
              {result.diff && (
                <pre className="diff">
                  {result.diff.split("\n").map((line, i) => (
                    <div key={i} className={line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : ""}>
                      {line || " "}
                    </div>
                  ))}
                </pre>
              )}
            </div>
          )}
        </section>

        <section className="dev-card grow">
          <h2>Event log (newest first)</h2>
          <div className="log">
            {log.map((l) => (
              <div key={l.id}>
                <span className="muted">{l.at}</span> {l.text}
              </div>
            ))}
          </div>
        </section>
      </div>

      <CallWindow
        state={call.state}
        roles={roles}
        talking={call.talking}
        onHangup={call.hangup}
        onRetryMic={call.retryMic}
      />
    </main>
  );
}
