# Views

## When to Use CBVs vs FBVs

This project uses **Class-Based Views (CBVs)** for most views and **Function-Based Views (FBVs)** for simple endpoints.

| Use     | When to Use                                                                                                                    |
| ------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **CBV** | Standard CRUD: list, detail, create, update, delete. Django's generic views handle the boilerplate.                            |
| **FBV** | Simple one-off endpoints: health checks, AJAX validation, webhooks, or views with unusual logic that doesn't fit CBV patterns. |

Examples of FBVs in this project: `healthz` (health check), `check_username` (AJAX validation), user registration views.

## Common CBV Types

| CBV            | When to Use                                                                 |
| -------------- | --------------------------------------------------------------------------- |
| `TemplateView` | GET-only pages with custom context (no object lookup needed)                |
| `ListView`     | Paginated lists, search results, filtered collections                       |
| `DetailView`   | Single object by pk/slug from URL                                           |
| `FormView`     | Forms that don't create/update a model directly                             |
| `CreateView`   | Model creation forms                                                        |
| `UpdateView`   | Model edit forms                                                            |
| `DeleteView`   | Deletion confirmation pages                                                 |
| `View`         | AJAX/JSON endpoints, multi-action POST handlers, or when generics don't fit |

## CBV Pattern

```python
class MyListView(CanAccessMaintainerPortalMixin, ListView):
    """Docstring describing the view's purpose."""

    # Always specify template explicitly, don't rely on auto-discovery
    template_name = "app/mymodel_list.html"

    # Name used in template: {% for item in items %}
    context_object_name = "items"

    # For paginated views. Omit for infinite scroll views.
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        """
        Runs before get() or post().

        Use to fetch objects from URL params that will be needed
        in multiple methods. Store on self for later access.
        """
        self.parent = get_object_or_404(Parent, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """
        Return the list of items for this view.

        Always optimize queries:
        - select_related() for ForeignKey/OneToOne (single JOIN)
        - prefetch_related() for ManyToMany/reverse FK (separate query)
        """
        return (
            MyModel.objects.filter(parent=self.parent)
            .select_related("foreign_key_field")
            .prefetch_related("many_to_many_field")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        """
        Add extra variables to the template context.

        Always call super() first to get the default context,
        then add your custom variables.
        """
        context = super().get_context_data(**kwargs)
        context["parent"] = self.parent
        context["stats"] = calculate_stats(self.parent)
        return context
```

## Access Control

Protect maintainer views with `CanAccessMaintainerPortalMixin`:

```python
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin

class MyProtectedView(CanAccessMaintainerPortalMixin, View):
    # Only logged-in maintainers can access
    ...
```

## Form Pre-filling via Session

`FormPrefillMixin` provides a generic mechanism for pre-filling a form field from session data. Any feature can seed a create form by storing data in the session, then redirecting to the create view.

```python
from the_flip.apps.core.mixins import FormPrefillMixin

class MyCreateView(FormPrefillMixin, CanAccessMaintainerPortalMixin, CreateView):
    ...
```

To pre-fill, store a dict in `request.session["form_prefill"]` with `field` (form field name) and `content` (value), then redirect to the create view. The mixin pops the session key in `get_initial()` so it's consumed once.

```python
request.session["form_prefill"] = {"field": "description", "content": "..."}
return redirect("my-create-view")
```

Used by wiki action buttons to pre-fill problem report, log entry, and part request forms.

## Safe Object Lookups

Use `get_object_or_404()` when fetching objects from URL parameters:

```python
# If no machine with this slug exists, Django returns a 404 page
# Without this, you'd get a 500 error (exposes that the object doesn't exist)
machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
```

## Mixins Over Base Classes

Use mixins (classes that call `super()`) instead of base classes. Python's MRO breaks when base classes don't call `super()` - sibling classes get skipped silently. Mixins compose safely; base classes don't.

## Infinite Scroll

List views use infinite scroll instead of traditional pagination:

- View returns a partial template for AJAX requests
- `infinite_scroll.js` handles loading more items on scroll
- See `LogListPartialView` for example implementation

## Multi-Model Feeds

When displaying activity from multiple models (logs, problems, parts) on a single timeline, use the unified feed in `core/feed.py`:

1. **Fetch limit+1 from each table** - Detects pagination without COUNT query ("countless pagination")
2. **Combine and sort in memory** - All models have `occurred_at`, sort descending
3. **Slice to page size** - Return just the requested page
4. **Return (items, has_next) tuple** - `has_next` derived from whether we fetched more than page_size

Pass `machine=` for a machine-scoped feed (uses `search_for_machine`) or omit it for the global feed (uses `search`, includes machine in `select_related`).

```python
from the_flip.apps.core.feed import get_feed_page, FEED_CONFIGS

# Machine-scoped feed
entries, has_next = get_feed_page(
    machine=self.machine,
    entry_types=feed_config.entry_types,
    page_num=page_num,
    search_query=search_query,
)

# Global feed (all machines)
entries, has_next = get_feed_page(
    page_num=page_num,
    search_query=search_query,
)
```

Use `PageCursor` when templates expect `page_obj` interface but Django's `Paginator` can't be used (multiple querysets).

## Query Optimization

Use `select_related` for ForeignKey/OneToOne (single JOIN) and `prefetch_related` for reverse/ManyToMany (separate query):

```python
# From maintenance/views/log_entries.py - actual project usage
LogEntry.objects.filter(machine=self.machine)
    .select_related("machine", "problem_report")
    .prefetch_related("maintainers__user", "media")
    .order_by("-occurred_at")
```

Add these in views or QuerySet methods where queries are built, not in model methods.

## View File Organization

Keep views in a single `views.py` until it exceeds ~500 lines (per [Django_Python.md](Django_Python.md)). When splitting:

1. **Extract shared patterns first** - Move duplicated logic to mixins or model managers _before_ splitting. Otherwise each new file inherits its own copy of the duplication.

2. **Convert to a `views/` package** - Create `views/__init__.py` with just a docstring (no re-exports).

3. **Split by domain, not technical layer** - Group views by feature area (e.g., `problem_reports.py`, `log_entries.py`), not by response format (e.g., `ajax_views.py`). Technical splits cause shotgun surgery—changing a feature touches multiple files.

4. **Update imports in urls.py** - Import directly from specific modules.
