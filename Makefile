# Common commands. Run `make` (or `make help`) to list them.

DEMO_REPO ?= $(abspath ../dunder-mifflin-infinity)
PAPERCLIP_URL ?= http://127.0.0.1:3100
PAPERCLIP_LOG ?= $(HOME)/.paperclip/dev-server.log
PORT ?= 8000

BACKEND_PY := backend/.venv/bin/python
PAPERCLIP_PY := paperclip/.venv/bin/python

.DEFAULT_GOAL := help
.PHONY: help setup test test-backend test-paperclip gateway paperclip-start paperclip-stop paperclip-status \
        paperclip-logs paperclip-ui down seed reset-repo reset-demo talk scenario avatar up up-mock frontend

help: ## List the commands
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Boot everything: Paperclip (if COMPANY_BACKEND=paperclip) + gateway + frontend; Ctrl+C stops
	PORT=$(PORT) scripts/up.sh

up-mock: ## Boot gateway + frontend on the mock company (no Paperclip needed)
	COMPANY_BACKEND=mock PORT=$(PORT) scripts/up.sh

frontend: ## Run only the frontend dev server (http://localhost:5173)
	cd frontend && npx vite --port 5173 --strictPort

setup: ## Full local setup: venvs, demo repo, local Paperclip, seeded company (safe to re-run)
	DEMO_REPO="$(DEMO_REPO)" PAPERCLIP_URL="$(PAPERCLIP_URL)" scripts/setup_local.sh

test: test-backend test-paperclip ## Run all tests

test-backend: ## Run the backend tests (gateway + company layer)
	cd backend && .venv/bin/pytest -q

test-paperclip: ## Run the Paperclip-side tests (seed script, skills, AGENTS.md)
	paperclip/.venv/bin/pytest -q paperclip/tests

gateway: ## Run the voice gateway on PORT (default 8000) with reload
	cd backend && .venv/bin/uvicorn main:app --reload --reload-dir gateway --reload-dir company --reload-dir roles --timeout-graceful-shutdown 2 --port $(PORT)

ROLE ?= eng_lead
talk: ## Call an agent with your mic (ROLE=ceo|cfo|eng_lead|engineer|sales_lead; needs requirements-dev.txt)
	cd backend && .venv/bin/python dev/talk.py $(ROLE)

avatar: ## Give an employee a lip-synced face: make avatar PHOTO=~/pic.jpg [FOR=engineer] (role from file name otherwise)
	cd backend && .venv/bin/python dev/set_avatar.py "$(PHOTO)" $(if $(FOR),--role $(FOR))

scenario: ## Automated demo-storyline check on the mock company (own gateway on :8001)
	cd backend && .venv/bin/python dev/scenario.py

paperclip-start: ## Start the local Paperclip if it isn't running (setup does this too)
	@curl -sf "$(PAPERCLIP_URL)/api/health" >/dev/null && echo "Paperclip already running" || \
		DEMO_REPO="$(DEMO_REPO)" PAPERCLIP_URL="$(PAPERCLIP_URL)" scripts/setup_local.sh

down: ## Stop everything: gateway (PORT), frontend (:5173) and Paperclip
	@-fuser -k $(PORT)/tcp 5173/tcp >/dev/null 2>&1 && echo "Gateway/frontend stopped" || echo "Gateway/frontend weren't running"
	@$(MAKE) --no-print-directory paperclip-stop

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

reset-repo: ## Put the demo repo back at the seeded bug and delete fix/* branches, local and on origin
	git -C "$(DEMO_REPO)" checkout -q main
	git -C "$(DEMO_REPO)" reset -q --hard seeded-bug
	@branches=$$(git -C "$(DEMO_REPO)" for-each-ref --format='%(refname:short)' 'refs/heads/fix/*'); \
	if [ -n "$$branches" ]; then git -C "$(DEMO_REPO)" branch -q -D $$branches; fi
	@remote=$$(git -C "$(DEMO_REPO)" ls-remote --heads origin 'fix/*' | sed 's|.*refs/heads/||'); \
	if [ -n "$$remote" ]; then git -C "$(DEMO_REPO)" push -q origin --delete $$remote; fi
	@git -C "$(DEMO_REPO)" fetch -q --prune origin
	@echo "$(DEMO_REPO) reset to seeded-bug, fix/* branches deleted"
