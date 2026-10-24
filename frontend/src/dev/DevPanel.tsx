// Temporary test panel for the gateway (mock or real). No audio playback or mic yet (C3):
// "Talk" sends silent fake mic audio, "Interrupt" sends a loud frame.
import { useEffect, useRef, useState } from "react";
import { gateway, GATEWAY_URL, USE_MOCK } from "../api";
import type { MockGateway } from "../api/mock";
import {
  BOARD_COLUMNS,
  CLOSE_ALREADY_ON_CALL,
  type AgentState,
  type Board,
  type CallEvent,
  type CallSocket,
  type Role,
  type TaskDetail,
} from "../api/types";

const mock = USE_MOCK ? (gateway as MockGateway) : null;
const FRAME_BYTES = 1920; // 40 ms of PCM16 24 kHz

interface CallView {
  roleId: string;
  name: string;
  status: string;
  lines: string[];
  partial: string;
  speaking: boolean;
  audioBytes: number;
}

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
  const [call, setCall] = useState<CallView | null>(null);
  const callRef = useRef<CallSocket | null>(null);

  const addLog = (text: string) =>
    setLog((prev) => [{ id: logId++, at: new Date().toLocaleTimeString(), text }, ...prev].slice(0, 40));

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

  function dial(role: Role) {
    const sock = gateway.openCall(role.id);
    if (callRef.current) {
      // Lets you check the one-call-at-a-time rule without losing the current call.
      sock.onClose((code) =>
        addLog(`second call to ${role.id} closed with ${code}${code === CLOSE_ALREADY_ON_CALL ? ' -> "Already on a call"' : ""}`),
      );
      return;
    }
    callRef.current = sock;
    const name = role.name.split(" ")[0];
    setCall({ roleId: role.id, name, status: "connecting", lines: [], partial: "", speaking: false, audioBytes: 0 });

    const update = (fn: (c: CallView) => CallView) => setCall((c) => (c ? fn(c) : c));
    sock.onEvent((e: CallEvent) => {
      if (e.type !== "transcript.assistant.delta") addLog(`CALL ${JSON.stringify(e)}`);
      switch (e.type) {
        case "call.started":
          return update((c) => ({ ...c, status: "live" }));
        case "transcript.assistant.delta":
          return update((c) => ({ ...c, partial: c.partial + e.text }));
        case "transcript.assistant.done":
          return update((c) => ({ ...c, partial: "", lines: [...c.lines, `${name}: ${e.text}`] }));
        case "transcript.user":
          return update((c) => ({ ...c, lines: [...c.lines, `You: ${e.text}`] }));
        case "barge_in":
          return update((c) => ({
            ...c,
            partial: "",
            lines: c.partial ? [...c.lines, `${name}: ${c.partial}… (interrupted)`] : c.lines,
          }));
        case "agent.speaking":
          return update((c) => ({ ...c, speaking: e.value }));
        case "task.started":
          return update((c) => ({ ...c, lines: [...c.lines, `[task started: ${e.title} -> ${e.assignee_role}]`] }));
        case "call.ended":
          return update((c) => ({ ...c, lines: [...c.lines, `[call ended by server: ${e.reason}]`] }));
        default:
          return;
      }
    });
    sock.onAudio((pcm) => update((c) => ({ ...c, audioBytes: c.audioBytes + pcm.byteLength })));
    sock.onClose((code) => {
      if (callRef.current === sock) callRef.current = null;
      addLog(`CALL closed with code ${code}`);
      update((c) => ({ ...c, status: `closed (${code})`, speaking: false }));
    });
  }

  function talk(seconds: number) {
    const frames = Math.round((seconds * 1000) / 40);
    for (let i = 0; i < frames; i++) callRef.current?.sendAudio(new ArrayBuffer(FRAME_BYTES));
  }

  function interrupt() {
    callRef.current?.sendAudio(new Int16Array(FRAME_BYTES / 2).fill(12000).buffer);
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

  const live = call !== null && !call.status.startsWith("closed");

  return (
    <main className="dev">
      <h1>Dunder Mifflin Infinity Voice™: gateway test panel</h1>
      <p className="muted">
        Gateway: {USE_MOCK ? "mock (VITE_MOCK=1)" : GATEWAY_URL}. No sound yet: audio arrives as a byte count until C3.
      </p>
      {USE_MOCK && (
        <ol className="muted steps">
          <li>Click Call next to anyone and wait for the greeting.</li>
          <li>Click "Talk 2 s": they delegate "Fix bulk discount" to Dwight and a card appears in todo.</li>
          <li>Watch it move to in_progress, then done ~10 s later, with a ping in the log.</li>
          <li>Click "Open result" to see the summary and diff.</li>
        </ol>
      )}
      {error && <p className="error">Can't reach the gateway: {error}</p>}

      <div className="dev-row">
        <section className="dev-card">
          <h2>Roles</h2>
          <ul className="plain">
            {roles.map((r) => (
              <li key={r.id}>
                <button onClick={() => dial(r)}>Call</button> {r.name} <span className="muted">({r.id})</span>{" "}
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
          <h2>Call {call && `with ${call.name}: ${call.status}`}</h2>
          {call ? (
            <>
              <p className="muted">
                {call.speaking ? "🔊 speaking" : "· silent"} · audio received: {(call.audioBytes / 48000).toFixed(1)} s
              </p>
              <div className="transcript">
                {call.lines.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
                {call.partial && <div className="muted">{call.name}: {call.partial}</div>}
              </div>
              <p>
                <button disabled={!live} onClick={() => talk(2)}>Talk 2 s</button>{" "}
                <button disabled={!live} onClick={interrupt}>Interrupt</button>{" "}
                <button disabled={!live} onClick={() => callRef.current?.hangup()}>Hang up</button>{" "}
                {mock && (
                  <button disabled={!live} onClick={() => mock.endActiveCall("idle_timeout")}>
                    End from server
                  </button>
                )}
              </p>
            </>
          ) : (
            <p className="muted">Not on a call.</p>
          )}
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
    </main>
  );
}
