# Testing Scaffold Reference

Use this document when setting up or re-generating the automated test harness from scratch. It captures the baseline runner, directory layout, and environment configuration. Day-to-day test authoring belongs in [`../Testing_Guide.md`](../Testing_Guide.md).

## Directory Layout

- Every Django app contains its own `tests/` package with `__init__.py` plus modules named `test_*.py`.
- Prefer grouping by concern (`tests/test_models.py`, `tests/test_forms.py`, `tests/test_views.py`) instead of giant catch-all files.
- Keep helper factories or fixtures under `tests/factories.py` or `tests/utils.py`. Avoid importing application code from `tests/__init__.py`.

## Default Runner & Settings

- All commands run through Django’s built-in runner: `python manage.py test`.
- `DJANGO_SETTINGS_MODULE` for automated runs must be `the_flip.settings.test`. This settings module should:
  - Use SQLite (in-memory if possible) for fast setup.
  - Configure `PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']`.
  - Turn off noisy logging and third-party integrations (email, caches).
  - Provide deterministic storage backends (`FileSystemStorage` + `StaticFilesStorage`) for forms/tests that touch files.

## Sample Data & Fixtures

- Management commands (`create_default_machines`, `create_sample_maintenance_data`, etc.) are for demo data only. Tests should create their own objects via factories or `setUp` methods so they remain deterministic.
- If reusable fixtures are needed (e.g., baseline machine catalog), store them under `tests/fixtures/` and reference them with `fixtures = ['machines.json']` in the relevant `TestCase`.
- Use Django’s `override_settings` decorator/context manager to inject storage paths, rate limit configuration, or toggle caches.

## Local & CI Execution

- Document the standard run command in `README.md`: from repo root run `python manage.py test`.
- If CI is added, the pipeline should at minimum run:
  1. `python -m compileall .`
  2. `python manage.py check`
  3. `python manage.py test`
- Keep these commands mirrored in local scripts (`make test`, `bin/run-tests.sh`) if the project adds tooling.

## Test Data Isolation

- Use `django.test.TestCase` whenever possible for automatic transaction rollback between tests.
- When tests must hit the database outside transactions (e.g., signal tests or integration with threads), switch to `TransactionTestCase` but keep their number small.
- Clear caches between tests if they influence behavior (`cache.clear()` in `setUp`), and isolate media uploads by overriding `DEFAULT_FILE_STORAGE`.

Reapply these conventions whenever the test harness is recreated to keep test execution fast, isolated, and portable.
