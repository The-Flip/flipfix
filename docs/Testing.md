# Automated Testing Guide

This is a guide for developers and AI assistants around running and creating automated tests.

## Running Tests
```bash
make test #runs test suite
```

## Suite Layout
Automated tests live in each app's `tests.py` file and follow Django's discovery rules (`Test*` classes, `test_*` methods).

When adding new tests:
 - Place them in the app-specific `tests.py` file next to the feature being exercised.
 - Keep each test independent by creating its own data in `setUp()` or factory helpers.
 - **Base classes:** Prefer `django.test.TestCase`, `TransactionTestCase`, and Django's `Client` for integration-style checks. These give you database isolation and fixtures without extra dependencies.


## Coverage
Prioritize highest-value flows:
1. **Domain models & business rules:** Core data behaviors, status transitions, and queryset/helpers should always have regression coverage.
2. **Forms & public views:** Anything that processes user input (especially rate-limiting or privacy-sensitive code) needs targeted tests.
3. **Authenticated workflows:** Staff-only dashboards, status updates, and permissions should have tests using authenticated users.
4. **APIs or integrations:** When new endpoints are added, cover success and failure cases; use Django's test client or `APIClient` if DRF enters the stack.

End-to-end browser coverage is intentionally out of scope right now to keep the suite fast. If we later need smoke tests, consider lightweight HTTP checks or component-level tests before introducing heavier tooling.
