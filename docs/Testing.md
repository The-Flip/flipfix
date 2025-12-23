# Automated Testing Guide

## Running Tests

```bash
make test              # Run full test suite
make test-fast         # Run fast tests only (exclude integration)
make test-models       # Run model tests only
```

### In CI

- GitHub Actions runs tests against PostgreSQL (matching production), while localhost `make test` uses SQLite for speed.
- GitHub Actions installs ffmpeg/ffprobe (for video transcoding) and runs the full suite, so `integration` tests are expected to pass there.
- Keep `integration` tests runnable locally, but you can use `make test-fast` for quick iteration if you don't have ffmpeg installed; env-dependent checks will be skipped when the binaries are missing. Unit tests mock ffmpeg/probe/upload to stay fast and quiet.

### Test Tags

| Tag | Use For |
|-----|---------|
| `models` | Model unit tests (no HTTP requests) |
| `views` | View tests that make HTTP requests |
| `ajax` | AJAX endpoints (combine with `views`: `@tag("views", "ajax")`) |
| `forms` | Form validation tests |
| `api` | External API endpoint tests |
| `feature_flags` | Tests for `constance` feature flag behavior |
| `integration` | Tests requiring external services (ffmpeg, S3, etc.) |
| `environment` | Environment-specific checks |
| `tasks` | Background task tests |
| `admin` | Django admin tests |
| `auth` | Authentication flow tests |
| `registration` | User registration tests |
| `terminals` | Shared terminal account tests |
| `public` | Public-facing (non-authenticated) page tests |

### Running Tests by Tag

```bash
python manage.py test --tag=models       # Model unit tests
python manage.py test --tag=views        # View/HTTP tests
python manage.py test --tag=api          # API endpoint tests
python manage.py test --exclude-tag=integration  # Skip slow tests
```


## Writing New Tests

1. Place tests in appropriate `test_*.py` file by feature (see below)
2. Add `@tag` decorators for selective execution
3. Use factory functions instead of manual object creation
4. Keep tests independent — each test sets up its own data
5. Use descriptive test names AND one-line docstrings; docstrings clarify intent and appear in test failure output

For mocking patterns (subprocess, HTTP, settings, time), see `maintenance/tests/test_tasks.py`.

### Test File Organization

Organize tests by **feature**, not by layer. Name files `test_<entity>_<action>.py`:

```text
the_flip/apps/maintenance/tests/
├── test_log_entry_create.py      # Log entry creation views
├── test_log_entry_detail.py      # Log entry detail view + AJAX
├── test_log_entry_list.py        # Log entry list views
├── test_log_entry_media.py       # Log entry media upload/delete
├── test_log_entry_models.py      # Log entry model unit tests
├── test_problem_report_create.py
├── test_problem_report_detail.py
...
```

**Why feature-based?**
- Run related tests together: `python manage.py test maintenance.tests.test_log_entry_create`
- Easier to find tests when debugging a specific feature
- Smaller files are easier to navigate than monolithic `test_views.py`

**Avoid layer-based naming** like `test_models.py`, `test_views.py`, `test_forms.py` — these grow large and mix unrelated features.


## Test Utilities

Shared utilities in `the_flip.apps.core.test_utils`:

### Factory Functions

| Factory | Use For |
|---------|---------|
| `create_machine()` | Creates machine model + instance |
| `create_problem_report()` | Problem report fixtures |
| `create_log_entry()` | Log entry fixtures |
| `create_maintainer_user()` | Users with access to the maintainer portal (most tests) |
| `create_user()` | Regular users without special permissions |
| `create_superuser()` | Admin/superuser access |
| `create_staff_user()` | Django admin access tests (sets `is_staff=True`) |
| `create_shared_terminal()` | Shared terminal user account fixtures |

#### Example

```python
from the_flip.apps.core.test_utils import (
    create_user, create_maintainer_user, create_superuser,
    create_machine_model, create_machine,
    create_problem_report, create_log_entry, create_shared_terminal,
)

maintainer = create_maintainer_user()  # Auto-generates username
machine = create_machine()  # Creates model + instance
maintainer = create_maintainer_user(username="alice", first_name="Alice")
```

### Test Mixins

Mixins provide reusable test fixtures and behaviors.

| Mixin | When to Use |
|-------|-------------|
| `TestDataMixin` | Most tests. Provides `self.machine`, `self.maintainer_user`, `self.regular_user`, `self.superuser` |
| `SuppressRequestLogsMixin` | View tests that expect 302/403/400 responses. Silences log noise. |
| `SharedAccountTestMixin` | Testing "who are you?" flows. Provides `self.shared_user`, `self.shared_maintainer`, `self.identifying_user`, `self.identifying_maintainer` |
| `TemporaryMediaMixin` | Media upload tests. Isolates MEDIA_ROOT per test. |

#### Put Mixins Before TestCase
When combining multiple mixins, **order matters** due to Python's MRO. Always put mixins before `TestCase`:

```python
class MyTests(SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase):
```

## Avoid Triggering The Secret Scanner

Do NOT hardcode strings like `"test-password-123"` because these trigger the `detect-secrets` pre-commit hook.

**User factories handle this automatically**:  `create_user()`, `create_maintainer_user()`, etc. generate random passwords internally.

For other tokens or secrets in tests, generate them in `setUp()`:

```python
import secrets

def setUp(self):
    self.test_token = secrets.token_hex(16)
```
