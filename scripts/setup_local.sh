#!/usr/bin/env bash
# One-command local setup: Python envs, the demo repo, a local Paperclip, and the seeded company.
# Safe to re-run: every step skips what's already done.
#
#   scripts/setup_local.sh
#
# Needs: Node >= 24.11, Python >= 3.11, git, Claude Code installed and logged in (agents run on your
# Claude login), and GitHub access to the private demo repo (gh auth login).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_REPO="${DEMO_REPO:-$(dirname "$REPO_ROOT")/dunder-mifflin-infinity}"
DEMO_REPO_SLUG="${DEMO_REPO_SLUG:-thomas-m1/dunder-mifflin-infinity}"
PAPERCLIP_URL="${PAPERCLIP_URL:-http://127.0.0.1:3100}"
PAPERCLIP_LOG="${PAPERCLIP_LOG:-$HOME/.paperclip/dev-server.log}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

step "Checking prerequisites"
command -v node >/dev/null || fail "Node.js not found (need >= 24.11)"
NODE_VERSION="$(node --version | sed 's/^v//')"
version_ge "$NODE_VERSION" 24.11.0 || fail "Node $NODE_VERSION is too old (need >= 24.11)"
command -v python3 >/dev/null || fail "python3 not found (need >= 3.11)"
PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
version_ge "$PY_VERSION" 3.11 || fail "Python $PY_VERSION is too old (need >= 3.11)"
command -v git >/dev/null || fail "git not found"
command -v claude >/dev/null || fail "Claude Code not found; install it and log in (Paperclip agents run on it)"
echo "node $NODE_VERSION, python $PY_VERSION, $(claude --version 2>/dev/null | head -1)"

step "Python environments"
for dir in backend paperclip; do
  [ -x "$REPO_ROOT/$dir/.venv/bin/python" ] || python3 -m venv "$REPO_ROOT/$dir/.venv"
  "$REPO_ROOT/$dir/.venv/bin/pip" install -q -r "$REPO_ROOT/$dir/requirements.txt"
  echo "$dir/.venv ready"
done

if [ ! -f "$REPO_ROOT/backend/.env" ]; then
  cp "$REPO_ROOT/backend/.env.example" "$REPO_ROOT/backend/.env"
  echo "Created backend/.env from .env.example: set BOSON_API_KEY (and ANTHROPIC_API_KEY) in it"
fi

step "Demo repo ($DEMO_REPO)"
if [ ! -d "$DEMO_REPO/.git" ]; then
  if command -v gh >/dev/null; then
    gh repo clone "$DEMO_REPO_SLUG" "$DEMO_REPO" \
      || fail "Couldn't clone $DEMO_REPO_SLUG; ask for collaborator access, then run 'gh auth login'"
  else
    git clone "https://github.com/$DEMO_REPO_SLUG.git" "$DEMO_REPO" \
      || fail "Couldn't clone $DEMO_REPO_SLUG; ask for collaborator access"
  fi
fi
git -C "$DEMO_REPO" fetch -q --tags origin 2>/dev/null || true
git -C "$DEMO_REPO" rev-parse -q --verify seeded-bug >/dev/null || fail "$DEMO_REPO has no 'seeded-bug' tag"
echo "demo repo ready (tag seeded-bug present)"

step "Paperclip ($PAPERCLIP_URL)"
if curl -sf "$PAPERCLIP_URL/api/health" >/dev/null; then
  echo "already running"
else
  mkdir -p "$(dirname "$PAPERCLIP_LOG")"
  if [ -f "$HOME/.paperclip/instances/default/config.json" ]; then
    paperclip_cmd=(run)
  else
    paperclip_cmd=(onboard --yes --no-install-service)
  fi
  echo "starting: npx paperclipai ${paperclip_cmd[*]} (log: $PAPERCLIP_LOG)"
  # Redirect the whole background group (not just npx) so no process keeps this script's stdout open.
  (cd "$HOME" && PAPERCLIP_TELEMETRY_DISABLED=1 exec nohup npx -y paperclipai@latest "${paperclip_cmd[@]}") \
    >"$PAPERCLIP_LOG" 2>&1 </dev/null &
  disown
  for _ in $(seq 1 240); do
    curl -sf "$PAPERCLIP_URL/api/health" >/dev/null && break
    sleep 1
  done
  curl -sf "$PAPERCLIP_URL/api/health" >/dev/null || fail "Paperclip didn't come up; see $PAPERCLIP_LOG"
  echo "running (stop it with: pkill -f paperclipai)"
fi

step "Seeding Dunder Mifflin"
(cd "$REPO_ROOT" && DEMO_REPO="$DEMO_REPO" PAPERCLIP_URL="$PAPERCLIP_URL" paperclip/.venv/bin/python paperclip/seed.py)

step "Done"
cat <<EOF
Paperclip UI:  $PAPERCLIP_URL
Use it from the gateway by setting COMPANY_BACKEND=paperclip in backend/.env, then:
  cd backend && .venv/bin/uvicorn main:app --reload --port 8000
Tests:  (cd backend && .venv/bin/pytest) && paperclip/.venv/bin/pytest paperclip/tests
EOF
