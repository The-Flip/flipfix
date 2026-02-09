# Automated Testing Guide

## Running Tests

```bash
make test              # Run Python tests (excludes integration)
make test-all          # Run full Python suite including integration tests
make test-models       # Run model tests only
make test-js           # Run JavaScript tests (requires: npm install)
```

### In CI

- GitHub Actions runs tests against PostgreSQL (matching production), while localhost `make test` uses SQLite for speed.
- GitHub Actions installs ffmpeg/ffprobe (for video transcoding) and runs the full suite, so `integration` tests are expected to pass there.
- Keep `integration` tests runnable locally, but `make test` excludes them by default for quick iteration if you don't have ffmpeg installed; env-dependent checks will be skipped when the binaries are missing. Unit tests mock ffmpeg/probe/upload to stay fast and quiet.

### Test Tags

Use these 6 tags to enable selective test execution. Each tag maps to a type of code you're editing:

| Tag           | Use For                                                        | When to Run                              |
| ------------- | -------------------------------------------------------------- | ---------------------------------------- |
| `models`      | Model/queryset logic, signals, managers                        | Editing models, managers, signals        |
| `views`       | HTTP request/response tests, template filters/tags             | Editing views, templates, URLs           |
| `forms`       | Form validation logic                                          | Editing form classes                     |
| `tasks`       | Background jobs (Django Q), async utilities, Discord bot logic | Editing async tasks, Discord integration |
| `admin`       | Django admin customizations                                    | Editing admin.py                         |
| `integration` | Tests requiring external services (ffmpeg, S3)                 | Exclude for fast local runs              |

### Running Tests by Tag

```bash
python manage.py test --tag=models              # Run model tests
python manage.py test --tag=views               # Run view tests
python manage.py test --exclude-tag=integration # Fast local runs
```

## Writing New Tests

### Test File Organization

**Use a `tests/` package**, not a single `tests.py` file. This keeps test files small and focused:

```text
the_flip/apps/myapp/
├── models.py
├── views.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    └── test_views.py
```

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

### Test Writing Rules

- Use descriptive test names with docstrings:
  - **One-line docstrings** for straightforward tests: `"""Staff can upload media."""`
  - **Multi-line docstrings** for regression tests or tests needing context to explain _why_ they exist
- Tags
  - Add [`@tag` decorators](#test-tags) for selective execution.
  - **Keep tags simple:** don't invent new tags or combine multiple tags. One tag per test class.
- Test data
  - Keep tests independent: each test sets up its own data
  - Use [factory functions](#factory-functions) instead of manual object creation
  - For mocking patterns (subprocess, HTTP, settings, time), see `maintenance/tests/test_tasks.py`

## Test Utilities

Shared utilities in `the_flip.apps.core.test_utils`:

### Factory Functions

| Factory                    | Use For                                                 |
| -------------------------- | ------------------------------------------------------- |
| `create_machine()`         | Creates machine model + instance                        |
| `create_problem_report()`  | Problem report fixtures                                 |
| `create_log_entry()`       | Log entry fixtures                                      |
| `create_maintainer_user()` | Users with access to the maintainer portal (most tests) |
| `create_user()`            | Regular users without special permissions               |
| `create_superuser()`       | Admin/superuser access                                  |
| `create_staff_user()`      | Django admin access tests (sets `is_staff=True`)        |
| `create_shared_terminal()` | Shared terminal user account fixtures                   |

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

| Mixin                      | When to Use                                                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestDataMixin`            | Most tests. Provides `self.machine`, `self.maintainer_user`, `self.maintainer`, `self.regular_user`, `self.superuser`                       |
| `SuppressRequestLogsMixin` | View tests that expect 302/403/400 responses. Silences log noise.                                                                           |
| `SharedAccountTestMixin`   | Testing "who are you?" flows. Provides `self.shared_user`, `self.shared_maintainer`, `self.identifying_user`, `self.identifying_maintainer` |
| `TemporaryMediaMixin`      | Tests that write actual files to disk (AJAX upload/delete). Isolates MEDIA_ROOT per test. Not needed when mocking file operations.          |

#### Put Mixins Before TestCase

When combining multiple mixins, **order matters** due to Python's MRO. Always put mixins before `TestCase`:

```python
class MyTests(SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase):
```

## Avoid Triggering The Secret Scanner

Do NOT hardcode strings like `"test-password-123"` because these trigger the `detect-secrets` pre-commit hook.

**User factories handle this automatically**: `create_user()`, `create_maintainer_user()`, etc. generate random passwords internally.

For other tokens or secrets in tests, generate them in `setUp()`:

```python
import secrets

def setUp(self):
    self.test_token = secrets.token_hex(16)
```

## JavaScript Tests

JavaScript modules that enhance markdown textareas are tested with [Vitest](https://vitest.dev/). Tests run in Node, not in the browser.

### Setup

```bash
npm install              # One-time: installs vitest
make test-js             # Run JS tests
```

### Architecture

JS modules use an IIFE pattern that conditionally exports pure functions for testing:

```javascript
(function (exports) {
  'use strict';

  function myPureFunction(value, start, end) {
    // String manipulation, returns { value, selectionStart, selectionEnd }
  }

  // DOM wiring (browser only)
  if (typeof document !== 'undefined') {
    // Event listeners, DOMContentLoaded, etc.
  }

  // Test exports (Node only)
  if (exports) {
    exports.myPureFunction = myPureFunction;
  }
})(typeof module !== 'undefined' ? module.exports : null);
```

This keeps the production behavior identical (IIFE, no globals) while making pure logic testable. DOM wiring is excluded from Node — integration-level tests use jsdom where needed.

### Test File Location

Test files live alongside their source in `the_flip/static/core/`:

```text
the_flip/static/core/
├── markdown_shortcuts.js          # Source
├── markdown_shortcuts.test.js     # Tests
```

### Writing JS Tests

```javascript
import { describe, it, expect } from 'vitest';
const { myPureFunction } = require('./my_module.js');

describe('myPureFunction', () => {
  it('does the expected thing', () => {
    const result = myPureFunction('hello', 0, 5);
    expect(result.value).toBe('expected output');
  });
});
```

## Testing on_commit Callbacks

Code that uses `transaction.on_commit()` (like video transcoding enqueue) won't execute callbacks during tests because `TestCase` wraps each test in a transaction that never commits. Use `captureOnCommitCallbacks`:

```python
with self.captureOnCommitCallbacks(execute=True):
    response = self.client.post(url, data)
# Callbacks have now executed, can assert on their side effects
mock_enqueue.assert_called_once_with(media_id=media.id, model_name="LogEntryMedia")
```
