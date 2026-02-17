# Tool paths — auto-detect .venv if present, fall back to system tools.
# Override individually with e.g. make test PYTHON=python3
PYTHON    ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
RUFF      ?= $(shell test -x .venv/bin/ruff && echo .venv/bin/ruff || echo ruff)
MYPY      ?= $(shell test -x .venv/bin/mypy && echo .venv/bin/mypy || echo python3 -m mypy)
DJLINT    ?= $(shell test -x .venv/bin/djlint && echo .venv/bin/djlint || echo djlint)
PRECOMMIT ?= $(shell test -x .venv/bin/pre-commit && echo .venv/bin/pre-commit || echo pre-commit)

.PHONY: help
help:
	@echo "Django project Makefile commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make bootstrap      - Install everything needed for development"
	@echo ""
	@echo "Development:"
	@echo "  make runserver      - Start development web server"
	@echo "  make runq           - Start development queue worker"
	@echo "  make runbot         - Start Discord bot"
	@echo "  make shell          - Start Django shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run fast suite (excludes integration)"
	@echo "  make test-all       - Run full test suite (includes integration)"
	@echo "  make test-models    - Run model tests only"
	@echo "  make test-js        - Run JavaScript tests (requires npm install)"
	@echo "  make eval-discord-bot-llm - Evaluate Discord bot LLM prompt"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Format and lint code (auto-fixes issues)"
	@echo "  make typecheck      - Check Python types"
	@echo "  make quality        - Lint and typecheck"
	@echo "  make precommit      - Run pre-commit hooks"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        - Run database migrations"
	@echo "  make migrations     - Create new migrations"
	@echo "  make superuser      - Create superuser"
	@echo "  make sample-data    - Create sample data (dev only)"
	@echo ""
	@echo "Documentation:"
	@echo "  make agent-docs     - Regenerate CLAUDE.md and AGENTS.md from source"
	@echo ""

.PHONY: bootstrap
bootstrap:
	scripts/bootstrap.sh

.PHONY: test
test:
	DJANGO_SETTINGS_MODULE=flipfix.settings.test $(PYTHON) manage.py test --keepdb --exclude-tag=integration

.PHONY: test-all
test-all:
	DJANGO_SETTINGS_MODULE=flipfix.settings.test $(PYTHON) manage.py test --keepdb

.PHONY: test-models
test-models:
	DJANGO_SETTINGS_MODULE=flipfix.settings.test $(PYTHON) manage.py test --keepdb --tag=models

.PHONY: test-js
test-js:
	npm test

.PHONY: eval-discord-bot-llm
eval-discord-bot-llm:
	$(PYTHON) manage.py eval_llm_prompt

.PHONY: runserver
runserver:
	@pkill -f "manage.py runserver" 2>/dev/null || true
	$(PYTHON) manage.py runserver

.PHONY: migrate
migrate:
	$(PYTHON) manage.py migrate

.PHONY: migrations
migrations:
	$(PYTHON) manage.py makemigrations

.PHONY: shell
shell:
	$(PYTHON) manage.py shell

.PHONY: superuser
superuser:
	$(PYTHON) manage.py createsuperuser

.PHONY: runq
runq:
	@pkill -f "manage.py qcluster" 2>/dev/null || true
	$(PYTHON) manage.py qcluster

.PHONY: runbot
runbot:
	@pkill -f "manage.py run_discord_bot" 2>/dev/null || true
	$(PYTHON) manage.py run_discord_bot

.PHONY: sample-data
sample-data:
	$(PYTHON) manage.py create_sample_data

.PHONY: lint
lint:
	$(RUFF) format .
	$(RUFF) check . --fix
	$(DJLINT) templates/ --reformat --quiet

.PHONY: typecheck
typecheck:
	$(MYPY) flipfix

.PHONY: quality
quality: lint typecheck
	@echo "All quality checks passed!"

.PHONY: precommit
precommit:
	@echo "Running pre-commit checks..."
	$(PRECOMMIT) run --all-files

.PHONY: agent-docs
agent-docs:
	python3 scripts/build_agent_docs.py
