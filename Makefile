.PHONY: help
help:
	@echo "Django project Makefile commands:"
	@echo ""
	@echo "Development:"
	@echo "  make runserver      - Start development web server"
	@echo "  make runq           - Start development queue worker"
	@echo "  make shell          - Start Django shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make format         - Auto-format code"
	@echo "  make lint           - Lint code"
	@echo "  make typecheck      - Check Python types"
	@echo "  make quality        - Format code and run all quality checks"
	@echo "  make precommit      - Run pre-commit hooks"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        - Run database migrations"
	@echo "  make migrations     - Create new migrations"
	@echo "  make reset-db       - Reset database and migrations"
	@echo "  make superuser      - Create superuser"
	@echo "  make sample-data    - Create sample data (dev only)"
	@echo ""

.PHONY: test
test:
	DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test --keepdb

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
	.venv/bin/python manage.py qcluster

.PHONY: reset-db
reset-db:
	./scripts/reset_migrations.sh

.PHONY: sample-data
sample-data:
	.venv/bin/python manage.py create_sample_data

.PHONY: lint
lint:
	.venv/bin/ruff check .
	.venv/bin/djlint templates/ --check

.PHONY: format
format:
	.venv/bin/ruff format .
	.venv/bin/djlint templates/ --reformat --quiet

.PHONY: typecheck
typecheck:
	.venv/bin/mypy the_flip

.PHONY: quality
quality: format lint typecheck
	@echo "All quality checks passed!"

.PHONY: precommit
precommit:
	@echo "Running pre-commit checks..."
	.venv/bin/pre-commit run --all-files
