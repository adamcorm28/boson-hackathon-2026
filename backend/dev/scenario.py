"""Rehearse the demo storyline end to end, with no Paperclip and no frontend.

Starts its own gateway on :8001 (mock company, simulated work bodies, fresh call memory),
then plays the user with TTS speech:
  1. Call Ryan: "What's going on with Infinity?" / "What do you recommend?" / "Okay, do it."
     -> Ryan must call delegate_task for Dwight.
  2. Hang up and call Jim: talk pipeline, stay on the line.
     -> Dwight's simulated fix finishes mid-call and Jim announces it.
Prints a PASS/FAIL checklist; exit code 1 if anything failed.

Usage (from backend/):
    .venv/bin/python dev/scenario.py                  # work takes 45 s (fits the call timeline)
    .venv/bin/python dev/scenario.py --work-seconds 30 --quiet
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from call_client import BACKEND, run_call, tts_pcm  # noqa: E402

RYAN = ["Hey Ryan, what's going on with Infinity?", "What do you recommend?", "Okay, do it."]
RYAN_RETRY = ["Please have Dwight fix the bulk discount bug now."]
JIM = ["Hey Jim, how's the pipeline looking?"]


class Checks:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, ok: bool | None, name: str, detail: str = "") -> bool:
        status = "PASS" if ok else ("WARN" if ok is None else "FAIL")
        self.rows.append((status, name, detail))
        print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
        return bool(ok)

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.rows)


async def collect_sse(url: str, out: list[tuple[str, dict]]) -> None:
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("GET", f"{url}/events") as resp:
            type_ = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    type_ = line[7:]
                elif line.startswith("data: ") and type_:
                    out.append((type_, json.loads(line[6:])))


def start_gateway(port: int, work_seconds: float, calls_dir: str, artifacts_dir: str) -> subprocess.Popen:
    env = {**os.environ, "COMPANY_BACKEND": "mock", "SIMULATE_WORK_SECONDS": str(work_seconds),
           "CALLS_DIR": calls_dir, "ARTIFACTS_DIR": artifacts_dir,
           "GATEWAY_PUBLIC_URL": f"http://localhost:{port}"}
    log = open(Path(calls_dir) / "gateway.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)],
                            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            if httpx.get(f"http://localhost:{port}/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    proc.terminate()
    raise SystemExit(f"gateway didn't start; see {log.name}")


def said(events: list[dict]) -> list[str]:
    return [e["text"] for e in events if e["type"] == "transcript.assistant.done"]


async def scenario(port: int, work_seconds: float, verbose: bool) -> Checks:
    http, ws = f"http://localhost:{port}", f"ws://localhost:{port}"
    checks = Checks()
    sse: list[tuple[str, dict]] = []
    for p in RYAN + RYAN_RETRY + JIM:  # pre-generate the user's speech so hang-up -> next call is quick
        await tts_pcm(p)
    sse_task = asyncio.create_task(collect_sse(http, sse))
    await asyncio.sleep(0.5)

    print("\n== Call 1: Ryan (eng_lead)")
    ryan = await run_call("eng_lead", RYAN, gateway=ws, verbose=verbose)
    delegations = [e for e in ryan if e["type"] == "tool.called" and e["name"] == "delegate_task"]
    if not delegations:
        checks.add(None, "Ryan delegated on 'Okay, do it.'", "he didn't; retrying with an explicit ask")
        ryan = await run_call("eng_lead", RYAN_RETRY, gateway=ws, verbose=verbose)
        delegations = [e for e in ryan if e["type"] == "tool.called" and e["name"] == "delegate_task"]
    started = [e for e in ryan if e["type"] == "task.started"]
    checks.add(bool(delegations), "Ryan called delegate_task",
               json.dumps(delegations[0]["args"]) if delegations else "never called it")
    if not started:
        checks.add(False, "task created for Dwight")
        sse_task.cancel()
        return checks
    task = started[0]
    checks.add(task["assignee_role"] == "engineer", "task assigned to Dwight (engineer)", task["title"])
    t_delegated = time.monotonic()

    print(f"\n== Call 2: Jim (sales_lead); Dwight finishes about {work_seconds:.0f}s after delegating")
    heard_ping = {"at": None}

    def announced(ev: dict) -> bool:
        if any(t == "ping" and d.get("task_id") == task["task_id"] for t, d in sse) and heard_ping["at"] is None:
            heard_ping["at"] = time.monotonic()
        return (heard_ping["at"] is not None and ev["type"] == "transcript.assistant.done"
                and time.monotonic() - heard_ping["at"] > 0.2)

    jim = await run_call("sales_lead", JIM, gateway=ws, verbose=verbose,
                         stay_seconds=work_seconds + 45, stop_when=announced)
    await asyncio.sleep(1)
    sse_task.cancel()

    def sse_for(type_):
        return [d for t, d in sse if t == type_ and d.get("task_id") == task["task_id"]]

    checks.add(any(d["status"] == "in_progress" for d in sse_for("task.updated")),
               "board moved the card to in_progress")
    done = sse_for("task.completed")
    checks.add(bool(done), "task.completed event", done[0]["summary"] if done else "")
    pings = sse_for("ping")
    ping_to = pings[0]["to_role"] if pings else "none"
    checks.add(ping_to == "sales_lead", "ping announced into Jim's call", f"to_role={ping_to}")
    if ping_to is None:
        print("    (the work finished between calls; try a larger --work-seconds)")
    lines = said(jim)
    mention = next((l for l in lines if "dwight" in l.lower()), None)
    checks.add(mention is not None, "Jim mentioned Dwight's result out loud", mention or " / ".join(lines[-2:]))
    knows_bug = any(w in " ".join(lines).lower() for w in ("discount", "infinity", "lackawanna"))
    checks.add(knows_bug or None, "Jim knew about the bug (call memory / briefing)")
    detail = httpx.get(f"{http}/tasks/{task['task_id']}").json()
    arts = detail.get("artifacts", [])
    checks.add(bool(detail.get("result_summary")) and bool(arts), "/tasks shows the result and an artifact",
               arts[0]["url"] if arts else "")
    if arts:
        checks.add(httpx.get(arts[0]["url"]).status_code == 200, "artifact downloads from /artifacts")
    print(f"\n  (delegation to announcement: {time.monotonic() - t_delegated:.0f}s)")
    return checks


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work-seconds", type=float, default=45)
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--quiet", action="store_true", help="only print the checklist")
    a = p.parse_args()
    tmp = tempfile.mkdtemp(prefix="scenario-")
    proc = start_gateway(a.port, a.work_seconds, tmp, str(Path(tmp) / "artifacts"))
    try:
        checks = asyncio.run(scenario(a.port, a.work_seconds, not a.quiet))
    finally:
        proc.terminate()
        proc.wait(10)
    print(f"\n{'FAILED' if checks.failed else 'ALL PASSED'}  (gateway log: {tmp}/gateway.log)")
    sys.exit(1 if checks.failed else 0)


if __name__ == "__main__":
    main()
