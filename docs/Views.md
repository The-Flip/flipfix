# Views

## When to Use CBVs vs FBVs

This project uses **Class-Based Views (CBVs)** for most views and **Function-Based Views (FBVs)** for simple endpoints.

| Use     | When to Use                                                                                                                    |
| ------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **CBV** | Standard CRUD: list, detail, create, update, delete. Django's generic views handle the boilerplate.                            |
| **FBV** | Simple one-off endpoints: health checks, AJAX validation, webhooks, or views with unusual logic that doesn't fit CBV patterns. |

Examples of FBVs in this project: `healthz` (health check), user registration views.

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
class MyListView(ListView):
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

Access control is handled globally by middleware and route annotations — individual views don't need mixins or decorators for auth. See [`docs/Auth.md`](Auth.md) for the full public access system.

### Route-level access with `path()`

Routes in `urls.py` use `flipfix.apps.core.routing.path()` which accepts an `access=` parameter:

```python
from flipfix.apps.core.routing import path

# Default (no access=): logged-in maintainer required
path("parts/", PartRequestListView.as_view(), name="part-request-list"),

# Public when PUBLIC_ACCESS_ENABLED toggle is on
path("machines/", MachineListView.as_view(), name="maintainer-machine-list", access="public"),

# Always open — infrastructure (login, healthz, QR form, API endpoints)
path("healthz", healthz, name="healthz", access="always_public"),

# Logged-in, any role — profile, password change
path("profile/", ProfileUpdateView.as_view(), name="profile", access="authenticated"),

# Superuser only
path("terminals/", TerminalListView.as_view(), name="terminal-list", access="superuser"),
```

| Level         | Who                            | `access=`         |
| ------------- | ------------------------------ | ----------------- |
| Always public | Anyone, regardless of toggle   | `"always_public"` |
| Public        | Unauthenticated when toggle on | `"public"`        |
| Authenticated | Any logged-in user             | `"authenticated"` |
| Maintainer    | Logged-in + portal permission  | `None` (default)  |
| Superuser     | Superuser                      | `"superuser"`     |

### Middleware stack

1. **`LoginRequiredMiddleware`** — Django 5.1 built-in. Redirects unauthenticated users to login unless the view is marked `login_not_required` (our `path()` handles this automatically for `access="always_public"` and `access="public"`).
2. **`MaintainerAccessMiddleware`** — checks the `can_access_maintainer_portal` permission globally. Views with `access="always_public"`, `"authenticated"`, or guest visitors on `"public"` routes are skipped automatically.
3. **`MaintainerActivityMiddleware`** — records `Maintainer.last_active_at` at most once per 24 h per authenticated user, gated by `cache.add()`. Runs on the response path (after the view), so it also fires on 403/error responses — for users without a `Maintainer` row, the underlying `.filter().update()` is a harmless no-op.

Views don't need `CanAccessMaintainerPortalMixin` — it was removed in favor of middleware.

See [`docs/Auth.md`](Auth.md) for the authoritative reference on the access control system.

### `render_to_string` and guest-aware templates

When using `render_to_string()` to render partials that contain guest-aware template logic (`{% if user.is_authenticated %}`), always pass `request=request` so the template gets a `RequestContext` with `user`:

```python
html = render_to_string("my_partial.html", context, request=request)
```

Without `request`, the `user` variable will be missing and authenticated maintainers will see the guest view.

## Form Pre-filling via Session

`FormPrefillMixin` provides a generic mechanism for pre-filling a form field from session data. Any feature can seed a create form by storing data in the session, then redirecting to the create view.

```python
from flipfix.apps.core.mixins import FormPrefillMixin

class MyCreateView(FormPrefillMixin, CreateView):
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
from flipfix.apps.core.feed import get_feed_page, FEED_CONFIGS

# Machine-scoped feed - pass the whole FeedConfig (not entry_types alone)
# so the per-source DB ordering travels with the entry-type list.
entries, has_next = get_feed_page(
    machine=self.machine,
    feed_config=feed_config,
    page_num=page_num,
    search_query=search_query,
)

# Global feed (all machines) - feed_config defaults to None, which means
# "all registered types, default -occurred_at ordering".
entries, has_next = get_feed_page(
    page_num=page_num,
    search_query=search_query,
)
```

Use `PageCursor` when templates expect `page_obj` interface but Django's `Paginator` can't be used (multiple querysets).

### `FeedConfig.source_order_by` invariant

Each `FeedConfig` declares a `source_order_by` tuple that controls the DB ordering applied to its participating sources. It defaults to `("-occurred_at",)`, which matches the in-memory merge-sort comparator in `get_feed_page`.

**Invariant:** if more than one source participates (`len(entry_types) != 1` — and that includes `entry_types=()`, the "all registered types" sentinel), `source_order_by` must remain `("-occurred_at",)`. `FeedConfig.__post_init__` enforces this at construction time and raises `ValueError` otherwise.

Why: pagination fetches an `offset + page_size + 1` slab from each source using `source_order_by`, then merges by `occurred_at` descending. If the per-source key disagrees with the merge key, the slab is the wrong window — a row that should be on the requested page can fall outside the per-source slab and silently vanish from the result.

Single-source tabs (e.g. Problems, which uses `("status_sort", "priority_sort", "-occurred_at")`) are exempt because `get_feed_page` skips the merge entirely when only one source participates and trusts the DB ordering.

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
