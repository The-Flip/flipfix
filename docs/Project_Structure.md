# Project Structure

This document describes the project's structure. It favors conventional Django practices: each business concern lives in its own app, shared utilities are centralized, and project-level settings stay thin.

```
the_flip/
├── manage.py
├── railpack.web.json / railpack.worker.json  # Per-service Railpack build configs
├── railway.toml / runtime.txt
├── requirements.txt / requirements.dev.txt
├── docs/                     # development guides, deployment docs, and plans
├── templates/                # Django templates organized by app
└── the_flip/                 # Django project package
    ├── __init__.py
    ├── settings/             # split settings (base/dev/test/prod_base/web/worker)
    ├── urls.py / asgi.py / wsgi.py
    ├── apps/
    │   ├── accounts/         # Maintainer profiles & auth glue
    │   ├── catalog/          # Catalog of pinball machines and models
    │   ├── maintenance/      # Problem reports, log entries
    │   ├── parts/            # Part request tracking and management
    │   ├── discord/          # Discord integration (webhooks and bot)
    │   └── core/             # Shared utilities & decorators
    └── static/               # Project-level static files
```

### Conventions

- Keep each app’s `models.py`, `admin.py`, `forms.py`, and `tests/` focused on that domain. For larger modules, split into packages (e.g., `catalog/models/machine.py`).
- Put routes in the root `urls.py` rather than per-app, to keep them all together and scannable.
- Use `settings/base.py` for shared defaults, `prod_base.py` for shared production config, then `web.py` (web production), `worker.py` (worker production), `dev.py` (local development), and `test.py` (CI/tests). Set `DJANGO_SETTINGS_MODULE` per environment.
