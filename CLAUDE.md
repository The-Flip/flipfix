# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django web app for managing pinball machine maintenance at The Flip pinball museum. Visitors report problems via QR codes on machines; maintainers track and resolve issues.

## Development Commands

```bash
# Development
make runserver      # Start dev web server
make runq           # Start background worker (required for video transcoding)
make shell          # Django shell

# Testing
make test           # Run test suite (uses test settings)

# Code Quality
make quality        # Format + lint + typecheck (run before committing)

# Database
make migrate        # Run migrations
make migrations     # Create new migrations
make reset-db       # Reset database and migrations
```

Run a single test:
```bash
DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test the_flip.apps.maintenance.tests.TestClassName.test_method_name
```

## Architecture

- **Web App**: Django serving public and admin interfaces
- **Background Worker**: Django Q task queue for async video transcoding
- **Database**: PostgreSQL (prod), SQLite (dev)
- **File Storage**: Local `/media/` in dev, persistent disk in prod

Settings split by environment: `the_flip/settings/{base,dev,test,prod}.py`. Set `DJANGO_SETTINGS_MODULE` accordingly.

## Project Structure

```
the_flip/
├── templates/              # Django templates organized by app
└── the_flip/
    ├── settings/           # Split settings (base/dev/test/prod)
    ├── apps/
    │   ├── accounts/       # Maintainer profiles & auth
    │   ├── catalog/        # Machine models/instances
    │   ├── maintenance/    # Problem reports, log entries, tasks
    │   └── core/           # Shared utilities & decorators
    └── static/             # Project-level static files
```

## Key Conventions

- Each app keeps `models.py`, `forms.py`, `views.py`, `admin.py`, `tests.py` focused on that domain
- Routes defined in root `urls.py` rather than per-app (keeps them scannable)
- Shared helpers go in `core` app, never in `__init__.py`
- Tests live in app-level `tests.py` files; use Django's `TestCase`

## Tool Usage

Use Context7 (`mcp__context7__resolve-library-id` and `mcp__context7__get-library-docs`) to look up current documentation when:
- Implementing Django features (models, views, forms, admin, etc.)
- Working with Python standard library or third-party packages
- Configuring Railway hosting and deployment
- Answering questions about library APIs or best practices

Use GitHub MCP (`mcp__github__*`) for repository operations:
- Repository: owner=`deanmoses`, repo=`the_flip`
- Creating, viewing, and updating issues and pull requests
- Checking PR status, reviews, and comments
- Listing commits and browsing repository contents

## AI Assistant Requirements

Before generating code or explanations, read the docs at `docs/README.md` and linked guides:
- `docs/Architecture.md` - System components
- `docs/Project_Structure.md` - Directory layout
- `docs/Django_Python.md` - Django conventions
- `docs/HTML_CSS.md` - CSS patterns and component classes
- `docs/Datamodel.md` - Domain models and relationships
- `docs/Testing.md` - Testing strategy

Do not introduce new conventions. Update docs when changing behavior.
