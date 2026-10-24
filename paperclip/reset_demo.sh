#!/usr/bin/env bash
# Reset everything a demo take changes (see reset_demo.py). Pass --skip-github to leave PRs alone.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec paperclip/.venv/bin/python paperclip/reset_demo.py "$@"
