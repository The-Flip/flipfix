# Django & Python Scaffold Reference

Use this document when spinning up or re-generating the Django project from scratch. It captures the baseline layout, settings modules, and deployment hooks that the project relies on. 

Day-to-day feature work should reference [`../Django_Python_Guide.md`](../Django_Python_Guide.md); this file exists so we can recreate the same foundation consistently.

## Base Project Layout

- Create the project package `the_flip` with Django’s `startproject`, then create domain apps (`accounts`, `catalog`, `maintenance`, `core`) via `startapp`. The intended tree is described in [`../Project_Structure.md`](../Project_Structure.md).
- Each app owns its own `models.py`, `forms.py`, `views.py`, `urls.py`, `tests/`, `templates/<app>/`, and optional `management/commands/` folder.
- Register app URLs from `the_flip/urls.py` using `path('accounts/', include('accounts.urls'))`, etc. Keep `core` reserved for shared utilities, template tags, and decorators.

## Settings Modules & Environment

- Split configuration into `the_flip/settings/base.py`, `dev.py`, `test.py`, and `prod.py`.
  - `base.py` defines installed apps, middleware, templates, database defaults (SQLite), static/media configuration, and logging skeleton.
  - `dev.py` enables `DEBUG = True`, uses local email backend, and adds development-only packages if needed.
  - `test.py` sets `PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']`, configures in-memory SQLite if possible, and disables expensive middleware.
  - `prod.py` enforces security flags (`SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SECURE`), turns off `DEBUG`, and configures WhiteNoise/static root for Render.
- Read secrets and Render-provided environment variables via `django-environ`/`python-decouple`. Required keys include `SECRET_KEY`, `ALLOWED_HOSTS`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and the email settings used by notifications.
- `DJANGO_SETTINGS_MODULE` should point to `the_flip.settings.dev` locally, `the_flip.settings.test` under automated tests, and `the_flip.settings.prod` in deployment scripts.

## Default Data & Management Commands

- Maintain dedicated commands for seeding demo data:
  - `python manage.py import_legacy_maintainers` (implemented in `accounts/management/commands/import_maintainers.py`)
  - `python manage.py import_machines` (implemented in `catalog/management/commands/import_machines.py`)
  - `python manage.py import_legacy_maintenance_records` (implemented in `maintenance/management/commands/import_maintenance_records.py`)
- These commands run via `build.sh` so every deploy to Render recreates the demo environment. When rebuilding locally, run the same sequence after `migrate`.

## Deployment Hooks

- `render.yaml` references `build.sh` for builds and `gunicorn the_flip.wsgi:application` for runtime. Keep those commands in sync with the project structure.
- `build.sh` must install `requirements.txt`, run migrations, collect static assets, and execute the data-seeding commands listed above.
- Rendering service variables:
  - `SECRET_KEY` generated automatically by Render.
  - `DEBUG=false`, `ALLOWED_HOSTS=the-flip.onrender.com`, `PYTHON_VERSION=3.13.2`.
  - Custom admin credentials are sourced from `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL`.

## Source Control & Tooling

- Include `build.sh`, `render.yaml`, `runtime.txt`, and `requirements.txt` at the repo root so hosting providers pick them up automatically.
- Store reusable scripts for loading data or exporting fixtures under `the_flip/maintenance/management/commands/` (or the relevant app) so they are importable during builds.
- Keep `.env.example` aligned with the settings modules (add new variables when settings change).

Recreate these conventions whenever the project is regenerated so the deployment pipeline and seeded demo experience remain intact.
