# Django & Python Conventions

## Rules

- **URLs**: All routes live in root `urls.py` (not per-app) for scannability
- **Shared code**: Put helpers in `core` app, never in `__init__.py`
- **Settings**: Layered modules (`settings/base.py`, `dev.py`, `test.py`, `prod_base.py`, `web.py`, `worker.py`). Set `DJANGO_SETTINGS_MODULE` accordingly.
- **Form styling**: Apply CSS classes from [HTML_CSS.md](HTML_CSS.md)
- **Views**: See [Views.md](Views.md) for CBV patterns and query optimization
- **Testing**: Follow [Testing.md](Testing.md) for strategy and coverage expectations
- **Don't silence linter warnings**: Don't add `# noqa`, `# type: ignore`, or similar comments to suppress warnings without explicit user approval. Fix the underlying issue instead, unless fixing looks complicated, then ask user.
- **Use Mixins, not base classes**: For shared behavior, use mixins (classes that call `super()`) instead of base classes. Python's MRO breaks when base classes don't call `super()` - sibling classes get skipped silently. Mixins compose safely; base classes don't.
- **Use `functools.partial` for deferred calls**: When passing callbacks to `transaction.on_commit()` or similar, use `partial(func, kwarg1=val1, kwarg2=val2)` instead of lambda. Always use keyword arguments with `partial` for clarity and testability. Avoid positional args since they're less readable and harder to verify in tests.
- **Secrets**: Use `python-decouple` to read from environment variables. Never hardcode keys, passwords or tokens.

## File Organization

Each app keeps `models.py`, `forms.py`, `views.py`, `admin.py`, `tests.py` focused on its domain. Split into packages (e.g., `models/task.py`) when modules exceed ~500 lines.

## Documentation

### Docstrings

Add docstrings to:
- All public classes (models, views, forms)
- Public methods that aren't self-explanatory from the name
- Template tags and filters (these are a public API)

Skip docstrings for:
- Private methods (prefixed with `_`)
- Django framework methods with obvious purpose (`get_queryset`, `clean`, `save`)
- Simple properties where the name says it all

When modifying code, verify existing docstrings are still accurate. Misleading documentation is worse than no documentation.

**Format**: Use simple descriptive docstrings. Type hints provide parameter and return types, so `Args:` and `Returns:` sections (Google/NumPy/Sphinx style) are unnecessary.

### General

- Update docs when behavior changes
- Use explicit TODO comments with rationale for unfinished work
