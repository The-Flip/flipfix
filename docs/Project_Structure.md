# Project Structure

This document describes the project's structure. It favors conventional Django practices: each business concern lives in its own app, shared utilities are centralized, and project-level settings stay thin.

```
the_flip/
├── manage.py
├── build.sh / railway.toml / runtime.txt / requirements.txt
├── docs/                     # development guides, deployment docs, and plans
├── templates/                # Django templates organized by app
└── the_flip/                 # Django project package
    ├── __init__.py
    ├── settings/             # split settings module (base/dev/test/prod)
    ├── urls.py / asgi.py / wsgi.py
    ├── apps/
    │   ├── accounts/         # Maintainer profiles & auth glue
    │   ├── catalog/          # Catalog of pinball machines and models
    │   ├── maintenance/      # Problem reports, log entries
    │   ├── webhooks/         # Webhook notifications to external services
    │   └── core/             # Shared utilities & decorators
    └── static/               # Project-level static files
```

### App responsibilities
- **accounts**: wraps Django’s `AUTH_USER_MODEL` with the Maintainer profile. Handles admin customization (list filters, field ordering) and any future features like maintainer onboarding or role management.
- **catalog**: owns Machine Models and Machine Instances, including public-facing metadata (educational content, credits, operational status). This app publishes read APIs/pages that the museum floor uses.
- **maintenance**: owns Problem Reports (visitor submissions), maintainer-created tasks, and Log Entries. Encapsulates workflows such as auto-closing tasks when machines are marked "good", rate-limiting submissions, and the "select-or-type" maintainer attribution control.
- **webhooks**: sends notifications to external services (Discord, Slack, etc.) when events occur. Configurable endpoints and per-event subscriptions via admin.
- **core**: shared helpers that don't belong to a single domain app—decorators, custom admin mixins, base templates, date utilities, etc.

### Conventions
- Keep each app’s `models.py`, `admin.py`, `forms.py`, and `tests/` focused on that domain. For larger modules, split into packages (e.g., `catalog/models/machine.py`).
- Prefer putting routes in the root `urls.py` rather than per-app, to keep them all together and scannable.
- Use `settings/base.py` for shared defaults and layer `dev.py` (local development), `test.py` (CI/automated tests), and `prod.py` (production). Point the `DJANGO_SETTINGS_MODULE` environment variable at the appropriate module per environment.
