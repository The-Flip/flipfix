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

**Non-strings** (ForeignKey, DateTimeField, IntegerField, FileField): Use both `blank=True, null=True` for optional fields.

```python
problem_report = models.ForeignKey(..., null=True, blank=True)
transcoded_file = models.FileField(blank=True, null=True)
```

**Temporal fields with defaults**: Use `default=timezone.now` for required timestamps that should default to "now":

```python
occurred_at = models.DateTimeField(default=timezone.now)  # Required, defaults to now
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
- `PartRequestQuerySet` - `active()`, `pending()`, `search()`, `search_for_machine()`
- `PartRequestUpdateQuerySet` - `search()`, `search_for_machine()`, `search_for_part_request()`

### SearchableQuerySetMixin

QuerySets with search methods inherit from `SearchableQuerySetMixin`:

```python
from the_flip.apps.core.models import SearchableQuerySetMixin

class LogEntryQuerySet(SearchableQuerySetMixin, models.QuerySet):
    ...
```

The mixin provides two helpers that DRY up the strip → empty-guard → filter → distinct boilerplate every search method needs:

- `_clean_query(query)` — strips whitespace, coerces `None` to `""`
- `_apply_search(query, q)` — returns `self` unchanged for empty queries, otherwise `self.filter(q).distinct()`

This ensures consistent behavior: whitespace is always stripped, empty queries always return the unfiltered queryset, and `.distinct()` is never forgotten (needed to deduplicate rows from JOINs).

### Composable Search Methods

For complex search logic with context-specific variants, use private `_build_*_q()` methods that return Q objects, then compose them in public methods.

#### Standard Field Patterns

When building search Q objects, include these fields consistently:

| Field Type       | Always Search                                                 |
| ---------------- | ------------------------------------------------------------- |
| User FK          | `username`, `first_name`, `last_name`                         |
| Freetext name    | The text field (e.g., `reported_by_name`) alongside any FK    |
| Status           | Include if users would search for it (e.g., "open", "closed") |
| Description/text | The main content field                                        |

#### Core Fields Helper

Each QuerySet has a `_build_*_q()` method for its own fields:

```python
class LogEntryQuerySet(SearchableQuerySetMixin, models.QuerySet):
    def _build_text_and_maintainer_q(self, query: str) -> Q:
        """Build Q object for this model's core searchable fields."""
        return (
            Q(text__icontains=query)
            | Q(maintainers__user__username__icontains=query)
            | Q(maintainers__user__first_name__icontains=query)
            | Q(maintainers__user__last_name__icontains=query)
            | Q(maintainer_names__icontains=query)
        )
```

#### Linked Record Helpers

When a model has a FK to another model, create a separate helper to search that linked model's fields. This enables bidirectional search—users can find records from either side of the relationship:

```python
class LogEntryQuerySet(SearchableQuerySetMixin, models.QuerySet):
    def _build_problem_report_q(self, query: str) -> Q:
        """Build Q object for searching linked problem report fields."""
        return (
            Q(problem_report__description__icontains=query)
            | Q(problem_report__reported_by_name__icontains=query)
            | Q(problem_report__reported_by_user__username__icontains=query)
            | Q(problem_report__reported_by_user__first_name__icontains=query)
            | Q(problem_report__reported_by_user__last_name__icontains=query)
        )
```

The parent model should have a corresponding helper for its children:

```python
class ProblemReportQuerySet(SearchableQuerySetMixin, models.QuerySet):
    def _build_log_entry_q(self, query: str) -> Q:
        """Build Q object for searching linked log entry fields."""
        return (
            Q(log_entries__text__icontains=query)
            | Q(log_entries__maintainers__user__username__icontains=query)
            | Q(log_entries__maintainers__user__first_name__icontains=query)
            | Q(log_entries__maintainers__user__last_name__icontains=query)
            | Q(log_entries__maintainer_names__icontains=query)
        )
```

#### Composing Search Methods

Compose the helpers into public search methods using `_clean_query` and `_apply_search`:

```python
class LogEntryQuerySet(SearchableQuerySetMixin, models.QuerySet):
    def search(self, query: str = ""):
        """Global search: all fields including machine name."""
        query = self._clean_query(query)
        return self._apply_search(
            query,
            self._build_text_and_maintainer_q(query)
            | Q(machine__model__name__icontains=query)
            | Q(machine__name__icontains=query)
            | self._build_problem_report_q(query),
        )

    def search_for_machine(self, query: str = ""):
        """Machine-scoped: excludes machine name, includes linked records."""
        query = self._clean_query(query)
        return self._apply_search(
            query,
            self._build_text_and_maintainer_q(query)
            | self._build_problem_report_q(query),
        )

    def search_for_problem_report(self, query: str = ""):
        """Problem-report-scoped: only this model's own fields."""
        query = self._clean_query(query)
        return self._apply_search(
            query,
            self._build_text_and_maintainer_q(query),
        )
```

**Key principles:**

1. **Private builders return Q objects** - Extract shared filter logic into `_build_*_q()` methods
2. **Separate helpers for core vs linked fields** - `_build_text_and_X_q()` for own fields, `_build_Y_q()` for each linked model
3. **Scoped variants adjust what's searched**:
   - Exclude redundant fields (machine name when on machine page)
   - Include linked record fields when context makes them relevant
4. **Bidirectional linked search** - If A links to B, searching A should find matches in B's fields, and vice versa
5. **Empty queries return `self`** - Let callers decide what to show when there's no search term (enforced by `SearchableQuerySetMixin`)
6. **Search methods are pure filters** - They don't apply ordering; caller is responsible for `.order_by()`
7. **`.distinct()` is always applied** - Joins on related fields can duplicate rows (enforced by `SearchableQuerySetMixin`)

**When to create scoped variants:**

Create `search_for_X()` methods when the search context changes what fields are relevant:

- `search()` - Global list: all fields including machine name
- `search_for_machine()` - Machine page: excludes machine name, includes linked record fields
- `search_for_problem_report()` - Problem report page: only the model's own fields (linked record is redundant)

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
