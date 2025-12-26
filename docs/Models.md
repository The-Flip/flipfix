# Model Patterns

This documents the model conventions used in this project. These are choices we've made, not Django basics.

## TimeStampedMixin

All models that need timestamps inherit from `TimeStampedMixin`:

```python
from the_flip.apps.core.models import TimeStampedMixin

class MyModel(TimeStampedMixin):
    # Automatically has created_at and updated_at
    name = models.CharField(max_length=200)
```

We use a mixin (not a base class) to discourage adding unrelated behavior.

## Choice Fields

Use Django's `TextChoices` for fields with fixed options:

```python
class ProblemReport(TimeStampedMixin):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

# Usage
if report.status == ProblemReport.Status.OPEN:
    ...
```

TextChoices provides type safety and IDE autocomplete.

## Field Nullability

**Strings** (CharField, TextField): Use `blank=True` only. Django stores empty strings, not NULL.

```python
description = models.TextField(blank=True)  # Stores "" when empty
```

**Non-strings** (ForeignKey, DateTimeField, IntegerField, FileField): Use both `blank=True, null=True`.

```python
problem_report = models.ForeignKey(..., null=True, blank=True)
work_date = models.DateTimeField(null=True, blank=True)
transcoded_file = models.FileField(blank=True, null=True)
```

## ForeignKey Relationships

Always specify `related_name` and choose `on_delete` deliberately:

```python
# CASCADE: Delete logs when machine is deleted
machine = models.ForeignKey(MachineInstance, on_delete=models.CASCADE, related_name="log_entries")

# SET_NULL: Keep report if user is deleted
reported_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="problem_reports_created")

# PROTECT: Prevent deleting referenced data
requested_by = models.ForeignKey(Maintainer, on_delete=models.PROTECT, related_name="part_requests")
```

## Custom QuerySets

Encapsulate reusable queries in QuerySet classes instead of repeating filter logic in views:

```python
class PartRequestQuerySet(models.QuerySet):
    def active(self):
        """Return part requests that are not cancelled."""
        return self.exclude(status=PartRequest.Status.CANCELLED)

    def pending(self):
        """Return part requests that are requested or ordered."""
        return self.filter(status__in=[PartRequest.Status.REQUESTED, PartRequest.Status.ORDERED])

class PartRequest(TimeStampedMixin):
    objects = PartRequestQuerySet.as_manager()

# Usage - clean, chainable, tested once
PartRequest.objects.active().pending()

# Instead of repeating this in every view:
PartRequest.objects.exclude(status="cancelled").filter(status__in=["requested", "ordered"])
```

The project uses this pattern in:
- `MachineInstanceQuerySet` - `visible()`, `active_for_matching()`
- `ProblemReportQuerySet` - `open()`, `search()`, `search_for_machine()`
- `LogEntryQuerySet` - `search()`, `search_for_machine()`, `search_for_problem_report()`
- `PartRequestQuerySet` - `active()`, `pending()`

### Composable Search Methods

For complex search logic with context-specific variants, use private `_build_*_q()` methods that return Q objects, then compose them in public methods:

```python
class LogEntryQuerySet(models.QuerySet):
    def _build_text_and_maintainer_q(self, query: str) -> Q:
        """Build Q object for core search fields."""
        return (
            Q(text__icontains=query)
            | Q(maintainers__user__username__icontains=query)
            | Q(maintainers__user__first_name__icontains=query)
        )

    def search(self, query: str = ""):
        """Global search across all fields."""
        query = (query or "").strip()
        if not query:
            return self
        return self.filter(
            self._build_text_and_maintainer_q(query)
            | Q(machine__model__name__icontains=query)
            | Q(problem_report__description__icontains=query)
        ).distinct()

    def search_for_machine(self, query: str = ""):
        """Machine-scoped: excludes machine name (redundant in context)."""
        query = (query or "").strip()
        if not query:
            return self
        return self.filter(
            self._build_text_and_maintainer_q(query)
            | Q(problem_report__description__icontains=query)
        ).distinct()
```

**Key principles:**

1. **Private builders return Q objects** - Extract shared filter logic into `_build_*_q()` methods
2. **Scoped variants exclude redundant fields** - When viewing a specific machine, searching for machine name is pointless
3. **Empty queries return `self`** - Let callers decide what to show when there's no search term
4. **Search methods are pure filters** - They don't apply ordering; caller is responsible for `.order_by()`
5. **Always call `.distinct()`** - Joins on related fields can duplicate rows

**When to create scoped variants:**

Create `search_for_X()` methods when fields become redundant in certain view contexts:
- `search()` - Global list: all fields
- `search_for_machine()` - Machine detail: excludes machine name
- `search_for_problem_report()` - Problem report detail: excludes machine and problem report fields

## Query Optimization

Don't add `select_related`/`prefetch_related` in model methods—add them in views or QuerySet methods where queries are built. See `docs/Views.md` for patterns.

### Querying Optional FileFields

For FileFields with `null=True, blank=True`, use `__gt=""` to exclude both NULL and empty values:

```python
# Get photos that have thumbnails (excludes both NULL and empty string)
photos = media.filter(thumbnail_file__gt="")

# NOT this—only catches empty string, misses NULL:
photos = media.exclude(thumbnail_file="")
```

The `__gt=""` pattern works because any non-empty path is greater than `""`, while both NULL and `""` fail the comparison.

## Model Checklist

When creating or modifying models:

- [ ] Add `__str__` method for admin/debugging
- [ ] Use appropriate field types (CharField with max_length, TextField for long text)
- [ ] Add `db_index=True` on fields used in filters/ordering
- [ ] Add `Meta` class with `ordering`, `verbose_name` if needed
- [ ] Write migration and test it both ways (migrate/rollback)
