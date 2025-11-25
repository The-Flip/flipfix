# Django & Python Conventions

Project-specific conventions for this codebase. For general Django/Python best practices, follow official Django docs and PEP 8.

## Project-Specific Rules

- **URLs**: All routes live in root `urls.py` (not per-app) for scannability
- **Shared code**: Put helpers in `core` app, never in `__init__.py`
- **Settings**: Layered modules (`settings/base.py`, `dev.py`, `test.py`, `prod.py`). Set `DJANGO_SETTINGS_MODULE` accordingly.
- **Secrets**: Use `python-decouple` to read from environment variables. Never hardcode keys or passwords.
- **Form styling**: Apply CSS classes from [HTML_CSS.md](HTML_CSS.md)
- **Testing**: Follow [Testing.md](Testing.md) for strategy and coverage expectations

## File Organization

Each app keeps `models.py`, `forms.py`, `views.py`, `admin.py`, `tests.py` focused on its domain. Split into packages (e.g., `models/task.py`) when modules exceed ~500 lines.

## Documentation

- Include docstrings summarizing intent on classes and complex functions
- Update docs when behavior changes
- Use explicit TODO comments with rationale for unfinished work
