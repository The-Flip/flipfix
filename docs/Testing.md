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

### Running Tests by Tag

```bash
python manage.py test --tag=models       # Model unit tests
python manage.py test --tag=views        # View/HTTP tests
python manage.py test --tag=api          # API endpoint tests
python manage.py test --exclude-tag=integration  # Skip slow tests
```

Available tags: `models`, `forms`, `views`, `api`, `ajax`, `admin`, `auth`, `registration`, `terminals`, `public`, `unit`, `integration`, `environment`, `tasks`

## Test Utilities

Shared utilities in `the_flip.apps.core.test_utils`:

### Factory Functions

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

**Which user factory to use:**
- `create_maintainer_user()` — For users accessing the maintainer portal (most tests)
- `create_user()` — For regular users without special permissions
- `create_superuser()` — For admin/superuser access
- `create_staff_user()` — Only for Django admin access tests (sets `is_staff=True`)

### TestDataMixin

```python
from the_flip.apps.core.test_utils import TestDataMixin

class MyTestCase(TestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        # Provides: self.machine, self.maintainer_user, self.regular_user, self.superuser
```

## Writing New Tests

1. Place tests in appropriate `test_*.py` file by domain
2. Add `@tag` decorators for selective execution
3. Use factory functions instead of manual object creation
4. Keep tests independent — each test sets up its own data
5. Use descriptive test names AND one-line docstrings; docstrings clarify intent and appear in test failure output

For mocking patterns (subprocess, HTTP, settings, time), see `maintenance/tests/test_tasks.py`.
