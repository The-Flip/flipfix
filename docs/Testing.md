# Automated Testing

This is a guide for developers and AI assistants around running and creating automated tests.

## Running Tests Locally
From the repo root:

```bash
make test           # runs entire suite
```

## Framework & Tooling
- **Base classes:** Prefer `django.test.TestCase`, `TransactionTestCase`, and Django's `Client` for integration-style checks. These give you database isolation and fixtures without extra dependencies.
- **No Selenium / browser automation:** Keep the suite lightweight and fast. Feature coverage that would require browser automation should be expressed as form/view tests using the Django test client.

## Suite Layout
Tests live under each app’s `tests/` package and follow Django's discovery rules (`test_*.py`, `Test*` classes).

When adding new tests:
1. Place them in the app-specific `tests/` package next to the feature being exercised.
2. Name files and classes with clear intent (`test_views_dashboard.py`, `AssignmentWorkflowTests`, etc.).
3. Keep each test independent by creating its own data in `setUp()` or factory helpers.


## Coverage Expectations
This is still a prototype headed toward v1, so prioritize the highest-value flows:
1. **Domain models & business rules:** Core data behaviors, status transitions, and queryset/helpers should always have regression coverage.
2. **Forms & public views:** Anything that processes user input (especially rate-limiting or privacy-sensitive code) needs targeted tests.
3. **Authenticated workflows:** Staff-only dashboards, status updates, and permissions should have tests using authenticated users.
4. **APIs or integrations:** When new endpoints are added, cover success and failure cases; use Django's test client or `APIClient` if DRF enters the stack.

End-to-end browser coverage is out of scope right now.
