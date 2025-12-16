# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Flipfix** is the maintenance tracking system for The Flip pinball museum. It's a Django web app where visitors report problems via QR codes on machines, and maintainers track, update, and resolve issues.

## Required Reading Before Implementation

STOP and read the relevant doc before writing code:

| Task | Read First |
|------|------------|
| Templates, HTML, CSS, Javascript | `docs/HTML_CSS.md` |
| Forms, inputs, validation | `docs/Forms.md` |
| Models, relationships | `docs/Datamodel.md` |
| Writing tests | `docs/Testing.md` |
| Django patterns, views | `docs/Django_Python.md` |
| System architecture | `docs/Architecture.md` |
| Directory layout | `docs/Project_Structure.md` |

Follow the patterns in these docs exactly. Do not introduce new conventions without asking. Update docs when changing behavior.

## PR Workflow

Before creating a pull request, run the code review agents on changed files:
1. `antipattern-scanner` - detects architectural violations
2. `clean-code-reviewer` - checks clean code principles
3. `code-smell-detector` - identifies maintainability hints

Use `/pre-pr-check` command to run the full pre-PR checklist, or spawn agents directly via Task tool. Address findings before submitting.

## Development Commands

```bash
# Development
make runserver      # Start dev web server
make runq           # Start background worker (required for video transcoding and web hooks)
make runbot         # Start Discord bot
make shell          # Django shell

# Testing
make test           # Run fast suite (excludes integration)
make test-all       # Run full suite (includes integration checks)
make test-classifier # Run classifier unit tests
make eval-classifier # Output classifier results to CSV

# Code Quality
make format         # Auto-format code
make lint           # Lint code
make typecheck      # Check Python types
make quality        # Format + lint + typecheck (run before committing)
make precommit      # Run pre-commit hooks

# Database
make migrate        # Run migrations
make migrations     # Create new migrations
make reset-db       # Reset database and migrations
make superuser      # Create superuser
make sample-data    # Create sample data (dev only)
```

Run a single test:
```bash
DJANGO_SETTINGS_MODULE=the_flip.settings.test .venv/bin/python manage.py test the_flip.apps.maintenance.tests.TestClassName.test_method_name
```

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


## Claude Code for the Web

When running on Claude Code for the web (no .venv), use these commands instead:

```bash
# Testing
DJANGO_SETTINGS_MODULE=the_flip.settings.test python3 manage.py test --keepdb

# Code Quality (run all three before committing)
ruff format .                    # Format code
ruff check .                     # Lint code
djlint templates/ --check        # Lint templates
/usr/local/bin/mypy the_flip     # Type check (MUST use full path - see note below)

# Database
DJANGO_SETTINGS_MODULE=the_flip.settings.dev python3 manage.py migrate
DJANGO_SETTINGS_MODULE=the_flip.settings.dev python3 manage.py makemigrations

# Django commands
DJANGO_SETTINGS_MODULE=the_flip.settings.dev python3 manage.py shell
DJANGO_SETTINGS_MODULE=the_flip.settings.dev python3 manage.py check
```

The SessionStart hook in `.claude/settings.json` automatically installs dependencies (ffmpeg, Python packages) and runs migrations.

**Important: mypy path issue** - An older mypy exists at `/root/.local/bin/mypy` which shadows the pip-installed version. This older version lacks access to django-stubs, causing "No module named 'mypy_django_plugin'" errors. Always use `/usr/local/bin/mypy` or `python3 -m mypy`.

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
    │   ├── discord/        # Discord bot integration
    │   ├── parts/          # Parts inventory tracking
    │   ├── webhooks/       # Webhook handlers
    │   └── core/           # Shared utilities & decorators
    └── static/             # Project-level static files
```

## Key Conventions

- Each app keeps `models.py`, `forms.py`, `views.py`, `admin.py`, `tests.py` focused on that domain
- Routes defined in root `urls.py` rather than per-app (keeps them scannable)
- Shared helpers go in `core` app, never in `__init__.py`
- Tests live in app-level `tests.py` files; use Django's `TestCase`

## Template Components

This project uses Django's `@register.inclusion_tag` and `@register.simple_block_tag` for reusable UI components. Components are defined in `the_flip/apps/core/templatetags/core_extras.py` and templates live in `templates/components/`.

### Available Components

Load with `{% load core_extras %}`, then use:

| Component | Type | Usage |
|-----------|------|-------|
| `two_column_layout` | Template | `{% extends "layouts/two_column.html" %}` with blocks: `mobile_actions`, `sidebar`, `main`. Sidebar block is auto-wrapped in sticky card. |
| `sidebar_section` | Block tag | `{% sidebar_section label="Stats" %}...{% endsidebar_section %}` - Section within sidebar |
| `editable_sidebar_card` | Block tag | `{% editable_sidebar_card editable=True edit_type="machine" current_value=slug csrf_token=csrf_token %}...{% endeditable_sidebar_card %}` - Sidebar card with edit dropdown |
| `stat_grid` | Inclusion tag | `{% stat_grid stats=stats_list %}` where stats is list of `{value, label, variant}` dicts |
| `empty_state` | Inclusion tag | `{% empty_state empty_message="No items." search_message="No results." is_search=query %}` - Empty/no results message |
| `timeline` | Block tag | `{% timeline %}...{% endtimeline %}` - Timeline container with vertical line |
| `timeline_entry` | Block tag | `{% timeline_entry icon="bug" variant="problem" %}...{% endtimeline_entry %}` |
| `pill` | Inclusion tag | `{% pill label="Open" variant="open" %}` - Status pill/badge |
| `form_label` | Simple tag | `{% form_label field %}` - Renders label with "(optional)" for non-required fields |
| `form_field` | Inclusion tag | `{% form_field field %}` - Renders field with label, input, help text, errors. Optional: `id`, `class_` |
| `form_fields` | Inclusion tag | `{% form_fields form %}` - Renders all visible fields in a form |
| `form_non_field_errors` | Inclusion tag | `{% form_non_field_errors form %}` - Renders non-field errors if any |
| `field_errors` | Inclusion tag | `{% field_errors form.field_name %}` - Renders field errors only (for custom field markup) |
| `field_help_text` | Inclusion tag | `{% field_help_text form.field_name %}` - Renders field help text only (for custom field markup) |
| `maintainer_autocomplete_field` | Inclusion tag | `{% maintainer_autocomplete_field form.name %}` - Autocomplete input for user search. Optional: `label`, `placeholder`, `size`, `show_label`, `required` |

**Form Field Marking**: Do NOT mark required fields with asterisks. The `form_field` component auto-appends "(optional)" to fields with `required=False`. For manual markup, add "(optional)" to the label or use `{% form_label field %}`. See `docs/Forms.md` for full form guidance.

### Pill Variants
- `neutral` (default), `open`, `closed`, `status-fixing`, `status-good`, `status-broken`
- `open` and `closed` are semantic aliases (open=broken styling, closed=good styling)

### Creating New Components

1. Add function to `the_flip/apps/core/templatetags/core_extras.py`:
   - Use `@register.inclusion_tag("components/name.html")` for components that render a template
   - Use `@register.simple_block_tag` for components that wrap content
2. Create template in `templates/components/` (for inclusion tags)
3. Document in this table

### Template Filters

| Filter | Usage | Description |
|--------|-------|-------------|
| `render_markdown` | `{{ text\|render_markdown }}` | Convert markdown to sanitized HTML with auto-linked URLs |
| `smart_date` | `{{ timestamp\|smart_date }}` | Render timestamp as `<time>` element for JS formatting |
| `display_name_with_username` | `{{ user\|display_name_with_username }}` | Returns "First Last (username)" or just "username" |
| `month_name` | `{{ month_num\|month_name }}` | Convert month number (1-12) to name |
| `problem_report_summary` | `{{ report\|problem_report_summary }}` | Concise summary: type + description |
| `problem_report_meta` | `{{ report\|problem_report_meta }}` | Reporter name + timestamp |
| `log_entry_meta` | `{{ entry\|log_entry_meta }}` | Maintainer names + timestamp |
| `getfield` | `{{ form\|getfield:"name" }}` | Get form field by name |
