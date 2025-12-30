.PHONY: help
help:
	@echo "Django project Makefile commands:"
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

.PHONY: test
test:
	DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test --keepdb --exclude-tag=integration

.PHONY: test-all
test-all:
	DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test --keepdb

.PHONY: test-models
test-models:
	DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test --keepdb --tag=models

.PHONY: eval-discord-bot-llm
eval-discord-bot-llm:
	.venv/bin/python manage.py eval_llm_prompt

.PHONY: runserver
runserver:
	@pkill -f "manage.py runserver" 2>/dev/null || true
	.venv/bin/python manage.py runserver

.PHONY: migrate
migrate:
	.venv/bin/python manage.py migrate

.PHONY: migrations
migrations:
	.venv/bin/python manage.py makemigrations

.PHONY: shell
shell:
	.venv/bin/python manage.py shell

.PHONY: superuser
superuser:
	.venv/bin/python manage.py createsuperuser

.PHONY: runq
runq:
	@pkill -f "manage.py qcluster" 2>/dev/null || true
	.venv/bin/python manage.py qcluster

.PHONY: runbot
runbot:
	@pkill -f "manage.py run_discord_bot" 2>/dev/null || true
	.venv/bin/python manage.py run_discord_bot

.PHONY: sample-data
sample-data:
	.venv/bin/python manage.py create_sample_data

.PHONY: lint
lint:
	.venv/bin/ruff format .
	.venv/bin/ruff check . --fix
	.venv/bin/djlint templates/ --reformat --quiet

.PHONY: typecheck
typecheck:
	.venv/bin/mypy the_flip

.PHONY: quality
quality: lint typecheck
	@echo "All quality checks passed!"

.PHONY: precommit
precommit:
	@echo "Running pre-commit checks..."
	.venv/bin/pre-commit run --all-files

.PHONY: agent-docs
agent-docs:
	python scripts/build_agent_docs.py
