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

Use these 6 tags to enable selective test execution. Each tag maps to a type of code you're editing:

| Tag | Use For | When to Run |
|-----|---------|-------------|
| `models` | Model/queryset logic, signals, managers | Editing models, managers, signals |
| `views` | HTTP request/response tests | Editing views, templates, URLs |
| `forms` | Form validation logic | Editing form classes |
| `tasks` | Background job tests (Django Q) | Editing async tasks |
| `admin` | Django admin customizations | Editing admin.py |
| `integration` | Tests requiring external services (ffmpeg, S3) | Exclude for fast local runs |

**Keep it simple.** Don't invent new tags or combine multiple tags. One tag per test class.

### Running Tests by Tag

```bash
python manage.py test --tag=models              # Run model tests
python manage.py test --tag=views               # Run view tests
python manage.py test --exclude-tag=integration # Fast local runs
```


## Writing New Tests

1. Place tests in appropriate `test_*.py` file by feature (see below)
2. Add `@tag` decorators for selective execution
3. Use factory functions instead of manual object creation
4. Keep tests independent — each test sets up its own data
5. Use descriptive test names with docstrings:
   - **One-line docstrings** for straightforward tests: `"""Staff can upload media."""`
   - **Multi-line docstrings** for regression tests or tests needing context to explain *why* they exist

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
| `TestDataMixin` | Most tests. Provides `self.machine`, `self.maintainer_user`, `self.maintainer`, `self.regular_user`, `self.superuser` |
| `SuppressRequestLogsMixin` | View tests that expect 302/403/400 responses. Silences log noise. |
| `SharedAccountTestMixin` | Testing "who are you?" flows. Provides `self.shared_user`, `self.shared_maintainer`, `self.identifying_user`, `self.identifying_maintainer` |
| `TemporaryMediaMixin` | Tests that write actual files to disk (AJAX upload/delete). Isolates MEDIA_ROOT per test. Not needed when mocking file operations. |

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

## Testing on_commit Callbacks

Code that uses `transaction.on_commit()` (like video transcoding enqueue) won't execute callbacks during tests because `TestCase` wraps each test in a transaction that never commits. Use `captureOnCommitCallbacks`:

```python
with self.captureOnCommitCallbacks(execute=True):
    response = self.client.post(url, data)
# Callbacks have now executed, can assert on their side effects
mock_enqueue.assert_called_once_with(media_id=media.id, model_name="LogEntryMedia")
```
