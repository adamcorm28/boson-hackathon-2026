#!/usr/bin/env bash
# Boot the whole app: (Paperclip if used) + voice gateway + frontend. Ctrl+C stops gateway and frontend.
#
#   scripts/up.sh            # company backend from backend/.env (COMPANY_BACKEND, default mock)
#   COMPANY_BACKEND=mock scripts/up.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PAPERCLIP_URL="${PAPERCLIP_URL:-http://127.0.0.1:3100}"

fail() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
port_owner() { ss -ltnp 2>/dev/null | grep ":$1 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

[ -x "$REPO_ROOT/backend/.venv/bin/uvicorn" ] || fail "backend/.venv missing; run 'make setup' first"
[ -f "$REPO_ROOT/backend/.env" ] || fail "backend/.env missing; copy backend/.env.example and set BOSON_API_KEY"

# Which company backend: env var wins, then backend/.env, then mock.
if [ -z "${COMPANY_BACKEND:-}" ]; then
  COMPANY_BACKEND="$(grep -E '^COMPANY_BACKEND=' "$REPO_ROOT/backend/.env" | tail -1 | cut -d= -f2 || true)"
fi
export COMPANY_BACKEND="${COMPANY_BACKEND:-mock}"

for port in "$PORT" "$FRONTEND_PORT"; do
  if pid="$(port_owner "$port")" && [ -n "$pid" ]; then
    fail "port $port is in use by pid $pid ($(ps -o cmd= -p "$pid" | cut -c1-80)); stop it first"
  fi
done

if [ "$COMPANY_BACKEND" = "paperclip" ]; then
  if ! curl -sf "$PAPERCLIP_URL/api/health" >/dev/null; then
    echo "Paperclip is down; starting it (make setup)..."
    "$REPO_ROOT/scripts/setup_local.sh" >/dev/null
  fi
  echo "Company: Paperclip at $PAPERCLIP_URL"
else
  echo "Company: mock (set COMPANY_BACKEND=paperclip in backend/.env for real agents)"
fi

if [ ! -d "$REPO_ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$REPO_ROOT/frontend" && npm install --silent)
fi
if [ ! -f "$REPO_ROOT/frontend/.env.local" ]; then
  printf 'VITE_GATEWAY_URL=http://localhost:%s\nVITE_MOCK=0\n' "$PORT" > "$REPO_ROOT/frontend/.env.local"
  echo "Created frontend/.env.local (real gateway on :$PORT)"
fi

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo; echo "Stopping gateway and frontend..."
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

prefix() { sed -u "s/^/$(printf '\033[%sm[%s]\033[0m ' "$1" "$2")/"; }

(cd "$REPO_ROOT/backend" && exec .venv/bin/uvicorn main:app --reload --reload-dir gateway --reload-dir company --reload-dir roles --timeout-graceful-shutdown 2 --port "$PORT") 2>&1 | prefix 36 gateway &
pids+=($!)
(cd "$REPO_ROOT/frontend" && exec npx vite --port "$FRONTEND_PORT" --strictPort) 2>&1 | prefix 35 frontend &
pids+=($!)

for _ in $(seq 1 30); do curl -sf "http://localhost:$PORT/roles" >/dev/null && break; sleep 1; done
printf '\n\033[1mOffice:  http://localhost:%s\033[0m   (gateway :%s, Ctrl+C to stop)\n\n' "$FRONTEND_PORT" "$PORT"
wait -n "${pids[@]}" || true
