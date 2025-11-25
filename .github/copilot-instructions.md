# Copilot Instructions for The Flip Pinball Museum Maintenance System

This guide enables AI coding agents to work productively in this Django-based codebase. Follow these instructions to ensure code, docs, and workflows align with project conventions and architecture.

## Big Picture Architecture
- **Web App:** Django project serving public and admin interfaces.
- **Background Worker:** Django Q task queue (run with `make runq`) for async video transcoding and other jobs.
- **Database:** PostgreSQL in production, SQLite for local/dev. Migrations managed via `make migrate`/`make migrations`.
- **File Storage:** Media files (photos/videos) stored locally in dev, persistent disk in production (`/media/`).

## Project Structure & Conventions
- Each domain lives in its own app under `the_flip/apps/`:
  - `accounts`: Maintainer profiles/auth
  - `catalog`: Machine models/instances
  - `maintenance`: Problem reports, logs
  - `core`: Shared utilities
- Settings split by environment: `settings/base.py`, `dev.py`, `test.py`, `prod.py`. Set `DJANGO_SETTINGS_MODULE` accordingly.
- Templates organized by app in `templates/<app>/`.
- Static files in `the_flip/static/`.
- Shared helpers go in `core`, not in `__init__.py`.

## Developer Workflows
- **Run dev server:** `make runserver`
- **Run background worker:** `make runq`
- **Run tests:** `make test` (uses test settings)
- **Code quality:** `make quality` (format, lint, typecheck)
- **Migrations:** `make migrate` / `make migrations`
- **Create sample data:** `make sample-data` (dev only)
- **Reset DB/migrations:** `make reset-db`
- **Create superuser:** `make superuser`

## Testing
- Tests live in each app's `tests/` package.
- Use Django's built-in runner (`python manage.py test`).
- No browser automation; use Django test client for integration.
- Coverage prioritized for models, forms, views, and business rules.

## HTML/CSS Patterns
- Use system font stack, no external fonts.
- Reference CSS tokens/variables from base stylesheet.
- No inline styles; use classes and BEM or namespaced modules.
- Components: `.btn`, `.card`, `.alert`, `.form-field`, `.list-card__meta`, etc.
- Accessibility: maintain focus outlines, WCAG AA contrast, semantic HTML.

## Data Model Highlights
- **Maintainer:** Linked to Django user, public names only.
- **Machine Model/Instance:** Rich metadata, unique slugs, enums for era/status/location.
- **Problem Report:** Visitor-submitted, rate-limited, open/closed status.
- **Log Entry:** Maintainer work logs, many-to-many maintainers, media attachments.

## Deployment & Operations
- PRs create ephemeral Railway environments for testing.
- Merging to `main` triggers production deploy via Railway.
- Rollbacks via Railway dashboard (code only, not DB migrations).
- Daily backups for DB and media files.
- Monitor logs and worker health in Railway dashboard or Django admin.

## AI Agent Requirements
- Always consult `docs/README.md` and linked guides before generating code or explanations.
- Cite relevant docs sections when answering or generating assets.
- Adhere to documented patterns—do not introduce new conventions.
- Update docs and README when changing behavior.
- Prefer explicit TODOs with rationale for unfinished work.

## Key References
- `README.md`, `docs/README.md`, `docs/Architecture.md`, `docs/Project_Structure.md`, `docs/Datamodel.md`, `docs/Django_Python.md`, `docs/HTML_CSS.md`, `docs/Testing.md`, `docs/Deployment.md`, `docs/Operations.md`

---
If any section is unclear or missing, ask for feedback and iterate to improve coverage.
