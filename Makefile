# Common commands. Run `make` (or `make help`) to list them.

DEMO_REPO ?= $(abspath ../dunder-mifflin-infinity)
PAPERCLIP_URL ?= http://127.0.0.1:3100
PAPERCLIP_LOG ?= $(HOME)/.paperclip/dev-server.log
PORT ?= 8000

BACKEND_PY := backend/.venv/bin/python
PAPERCLIP_PY := paperclip/.venv/bin/python

.DEFAULT_GOAL := help
.PHONY: help setup test test-backend test-paperclip gateway paperclip-start paperclip-stop paperclip-status \
        paperclip-logs paperclip-ui seed reset-repo reset-demo

help: ## List the commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Full local setup: venvs, demo repo, local Paperclip, seeded company (safe to re-run)
	DEMO_REPO="$(DEMO_REPO)" PAPERCLIP_URL="$(PAPERCLIP_URL)" scripts/setup_local.sh

test: test-backend test-paperclip ## Run all tests

test-backend: ## Run the backend tests (gateway + company layer)
	cd backend && .venv/bin/pytest -q

test-paperclip: ## Run the Paperclip-side tests (seed script, skills, AGENTS.md)
	paperclip/.venv/bin/pytest -q paperclip/tests

gateway: ## Run the voice gateway on PORT (default 8000) with reload
	cd backend && .venv/bin/uvicorn main:app --reload --port $(PORT)

paperclip-start: ## Start the local Paperclip if it isn't running (setup does this too)
	@curl -sf "$(PAPERCLIP_URL)/api/health" >/dev/null && echo "Paperclip already running" || \
		DEMO_REPO="$(DEMO_REPO)" PAPERCLIP_URL="$(PAPERCLIP_URL)" scripts/setup_local.sh

paperclip-stop: ## Stop the local Paperclip
	@pkill -f '[p]aperclipai' && echo "Paperclip stopped" || echo "Paperclip wasn't running"

paperclip-status: ## Is Paperclip up?
	@curl -sf "$(PAPERCLIP_URL)/api/health" >/dev/null && echo "Paperclip up at $(PAPERCLIP_URL)" || echo "Paperclip down"

paperclip-logs: ## Follow the Paperclip server log
	tail -f "$(PAPERCLIP_LOG)"

paperclip-ui: ## Print the Paperclip UI address
	@echo "$(PAPERCLIP_URL)"

seed: ## Create or refresh Dunder Mifflin in Paperclip (idempotent)
	DEMO_REPO="$(DEMO_REPO)" PAPERCLIP_URL="$(PAPERCLIP_URL)" $(PAPERCLIP_PY) paperclip/seed.py

reset-demo: ## Full reset between takes: Paperclip tasks/runs/sessions, demo repo, GitHub PRs, artifacts, re-seed
	paperclip/reset_demo.sh

reset-repo: ## Put the demo repo back at the seeded bug (discards local changes there)
	git -C "$(DEMO_REPO)" checkout -q main
	git -C "$(DEMO_REPO)" reset -q --hard seeded-bug
	@echo "$(DEMO_REPO) reset to seeded-bug"
