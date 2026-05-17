# Markdown: Linking to Other Records

All of Flipfix's various types of records -- Problem Reports, Log Entries, Parts Requests and Wiki Pages -- support markdown. In that markdown, you can link from any type of record to any other type of record.

The only markdown field this does NOT apply to is the public problem report submission form.

## How to Use It

Type `[[` in any text field to insert links to other records. You'll get an autocomplete that helps you find any record in the system. It will create markdown like:

```
[[machine:attack-from-mars]]
```

When rendered, it turns into a clickable URL to that record.

## Examples

- Wiki docs can link to other wiki docs.
- The repair guide wiki doc for the Blackout machine could link directly to the Blackout machine's detail page in Flipfix.
- A troubleshooting wiki doc could reference the specific problem reports that inspired it.
- A log entry could be able to reference the troubleshooting wiki doc that helped solve it.
- A log entry could be able to reference a part request that's holding up completion of the work.

## Architecture

The system supports two kinds of link types:

- **Slug-based** (e.g., `[[machine:blackout]]`): For models with human-readable slugs. The authoring format uses the slug, while the storage format uses the database PK (`[[machine:id:42]]`).
- **ID-based** (e.g., `[[problem:7]]`): For models without slugs. The format is the same in both authoring and storage.

Eight link types are registered across five apps:

| Type                | App         | Format     | Model               |
| ------------------- | ----------- | ---------- | ------------------- |
| `machine`           | catalog     | slug-based | `MachineInstance`   |
| `model`             | catalog     | slug-based | `MachineModel`      |
| `problem`           | maintenance | ID-based   | `ProblemReport`     |
| `log`               | maintenance | ID-based   | `LogEntry`          |
| `partrequest`       | parts       | ID-based   | `PartRequest`       |
| `partrequestupdate` | parts       | ID-based   | `PartRequestUpdate` |
| `page`              | wiki        | slug-based | `WikiPageTag`       |
| `user`              | accounts    | slug-based | `auth.User`         |

The `user` type is scoped to directory-visible maintainers — see [`Scoping`](#scoping) for how `target_queryset` keeps autocomplete, save-time validation, render-time resolution, and reference syncing all in agreement about which targets are linkable.

### Registry pattern

Core provides the framework in `core/markdown_links.py`. Each app registers its link types in `AppConfig.ready()`. Core has zero imports from other apps.

```
catalog/apps.py      →  register(LinkType(name="machine", ...))
maintenance/apps.py  →  register(LinkType(name="problem", ...))
parts/apps.py        →  register(LinkType(name="partrequest", ...))
wiki/apps.py         →  register(LinkType(name="page", ...))
```

### Data flow

```
User types [[machine:blackout]]
         ↓
Form clean_<field>() calls convert_authoring_to_storage()
         ↓
Stored as [[machine:id:42]] in database
         ↓
View calls sync_references() to update RecordReference table
         ↓
render_markdown filter calls render_all_links() → HTML link
```

`render_all_links()` accepts optional parameters:

- `base_url`: When provided, URLs are absolute (e.g., `https://flipfix.the-flip.com/machines/blackout/`). Used by Discord webhook handlers.
- `plain_text`: When `True`, renders just the label with no link syntax. Used for short preview snippets where markdown links would be truncated.

For slug-based types, `convert_storage_to_authoring()` converts back when loading content into an edit form (e.g., `[[machine:id:42]]` → `[[machine:blackout]]`).

For ID-based types, no conversion is needed — the format is the same in both directions.

### Key modules

| Module                               | Purpose                                                          |
| ------------------------------------ | ---------------------------------------------------------------- |
| `core/markdown_links.py`             | `LinkType` dataclass, registry, conversion, rendering, sync      |
| `core/models.py`                     | `RecordReference` model (generic link tracking via contenttypes) |
| `core/views/link_targets.py`         | `LinkTypesView` and `LinkTargetsView` API endpoints              |
| `core/templatetags/markdown_tags.py` | `render_markdown` filter calls `render_all_links()`              |
| `static/core/link_autocomplete.js`   | `[[` autocomplete UI (fully server-driven)                       |

## Adding a New Link Target

A "link target" is a record type that other records can link **to**. For example, `MachineInstance` is a target because you can write `[[machine:blackout]]` in a log entry.

### Step 1: Register the link type

In your app's `apps.py`, register a `LinkType` in the `ready()` method:

```python
# myapp/apps.py
class MyAppConfig(AppConfig):
    ...
    def ready(self):
        self._register_link_types()

    @staticmethod
    def _register_link_types():
        from flipfix.apps.core.markdown_links import LinkType, register

        def _serialize_widget(obj):
            return {"label": obj.name, "ref": obj.slug}

        register(
            LinkType(
                name="widget",                      # Used in [[widget:...]] syntax
                model_path="myapp.Widget",           # For apps.get_model()
                slug_field="slug",                   # Set for slug-based; omit for ID-based
                label="Widget",                      # Human-readable name in type picker
                description="Link to a widget",      # Shown below label in type picker
                url_name="widget-detail",            # URL pattern name for reverse()
                url_kwarg="slug",                    # Kwarg name for reverse()
                url_field="slug",                    # Model field to get kwarg value
                autocomplete_search_fields=("name", "slug"),
                autocomplete_ordering=("name",),
                autocomplete_serialize=_serialize_widget,
            )
        )
```

### Step 2: Understand the three different "labels"

There are three separate labels for each link type. They serve different purposes and are often different:

| Label                   | Where it appears                                               | How to configure                                      |
| ----------------------- | -------------------------------------------------------------- | ----------------------------------------------------- |
| **Type picker label**   | Dropdown after typing `[[`                                     | `LinkType.label` and `LinkType.description`           |
| **Rendered link text**  | In rendered markdown (e.g., "[Blackout](/machines/blackout/)") | `LinkType.label_field` or `LinkType.get_label`        |
| **Autocomplete result** | Search dropdown after selecting a type                         | `autocomplete_serialize` return value's `"label"` key |

### Step 3: Understand the `ref` contract

The `autocomplete_serialize` function must return `{"label": ..., "ref": ...}` where:

- `"label"` is displayed in the search results dropdown
- `"ref"` is the authoring-format key inserted into `[[type:ref]]`

For slug-based types, `ref` is the slug (e.g., `"blackout"`).
For ID-based types, `ref` is `str(obj.pk)` (e.g., `"42"`).

The JS is fully server-driven — it inserts `[[type:ref]]` exactly as returned by the API, with no knowledge of whether the type is slug-based or ID-based.

### Step 4: Write tests

Add tests in `myapp/tests/` covering:

- Rendering: `[[widget:slug]]` and `[[widget:id:N]]` both render as clickable markdown links
- Conversion: `[[widget:slug]]` converts to `[[widget:id:N]]` on save (slug-based only)
- Autocomplete: API returns results with correct `label` and `ref` fields
- Broken links: deleted targets render as `*[broken link]*`

See `core/tests/test_link_rendering.py`, `core/tests/test_link_conversion.py`, and `core/tests/test_link_targets_api.py` for examples.

### `LinkType` field reference

**Identity:**

| Field         | Required | Description                                                         |
| ------------- | -------- | ------------------------------------------------------------------- |
| `name`        | Yes      | The string in `[[name:...]]`. Must be unique.                       |
| `model_path`  | Yes      | Django app label + model name (e.g., `"catalog.MachineInstance"`)   |
| `label`       | Yes\*    | Human-readable name for the type picker (e.g., `"Machine"`)         |
| `description` | Yes\*    | Brief description for the type picker (e.g., `"Link to a machine"`) |

\*Required if providing `autocomplete_serialize`.

**Format:**

| Field        | Default | Description                                                                 |
| ------------ | ------- | --------------------------------------------------------------------------- |
| `slug_field` | `None`  | Set to the model's slug field name for slug-based types. `None` = ID-based. |

#### Scoping

`target_queryset` defines the set of records a link type considers linkable. It is a callable `(model) -> QuerySet` that defaults to `model.objects.all()`. The same scope is used by save-time conversion, render-time lookup, autocomplete, and reference syncing — all in agreement.

Use it when a record exists in the database but should not be linkable — e.g. the `user` type uses it to scope to directory-visible maintainers so deactivated users, shared kiosk accounts, and orphan users without a profile page are hidden from `[[user:…]]`.

Records outside the scope behave exactly like deleted records:

- Autocomplete does not surface them.
- `convert_authoring_to_storage("[[type:slug]]")` raises `ValidationError`.
- Render output for `[[type:id:N]]` is `*[broken link]*`.
- `convert_storage_to_authoring("[[type:id:N]]")` leaves the storage token unchanged — the edit form shows the raw token so the author can decide what to do. Broken-link text is strictly a render-time concern.
- `sync_references()` prunes the `RecordReference` row on the next save (and recreates it if the record re-enters scope — self-healing).

**Rendering (in markdown output):**

| Field            | Default  | Description                                                |
| ---------------- | -------- | ---------------------------------------------------------- |
| `url_name`       | `""`     | URL pattern name for `reverse()`                           |
| `url_kwarg`      | `"pk"`   | Kwarg name passed to `reverse()`                           |
| `url_field`      | `"pk"`   | Model field to get the kwarg value from                    |
| `label_field`    | `"name"` | Model field for rendered link text                         |
| `get_url`        | `None`   | Override function `(obj) -> str` for irregular URLs        |
| `get_label`      | `None`   | Override function `(obj) -> str` for irregular labels      |
| `select_related` | `()`     | Tuple of related fields to prefetch during batch rendering |

**Authoring format (slug-based types only):**

| Field               | Default | Description                                                           |
| ------------------- | ------- | --------------------------------------------------------------------- |
| `authoring_lookup`  | `None`  | Custom `(model, raw_values) -> {key: obj}` for irregular slug parsing |
| `get_authoring_key` | `None`  | Custom `(obj) -> str` for storage-to-authoring key derivation         |

Most slug-based types don't need these — the defaults use `slug_field` directly. Wiki pages override both because their authoring key is `tag/slug` (e.g., `docs/getting-started`).

**Autocomplete:**

| Field                         | Default | Description                                                                                |
| ----------------------------- | ------- | ------------------------------------------------------------------------------------------ |
| `autocomplete_search_fields`  | `()`    | Model fields to search with `__icontains`                                                  |
| `autocomplete_ordering`       | `()`    | Default queryset ordering                                                                  |
| `autocomplete_select_related` | `()`    | Related fields to prefetch for serialization                                               |
| `autocomplete_serialize`      | `None`  | `(obj) -> {"label": str, "ref": str}`. Required for the type to appear in the `[[` picker. |

**Other:**

| Field        | Default        | Description                                                                         |
| ------------ | -------------- | ----------------------------------------------------------------------------------- |
| `is_enabled` | `lambda: True` | Runtime toggle. Return `False` to hide the type without unregistering.              |
| `sort_order` | `100`          | Integer controlling position in the `[[` type picker — lower numbers appear higher. |

Existing `sort_order` values, for reference when slotting a new type:
`page` (10), `machine` (20), `problem` (30), `log` (40), `partrequest` (50), `partrequestupdate` (60), `model` (70), `user` (80).

## Adding a New Link Source

A "link source" is a model whose text field supports `[[type:ref]]` links. For example, `LogEntry.text` is a source because maintainers can type `[[machine:blackout]]` in it.

There are four integration points:

### 1. Form: convert authoring to storage on save

In the form's `clean_<field>()` method, convert `[[machine:blackout]]` to `[[machine:id:42]]`:

```python
from flipfix.apps.core.markdown_links import convert_authoring_to_storage

def clean_text(self):
    text = self.cleaned_data.get("text", "")
    if text:
        text = convert_authoring_to_storage(text)
    return text
```

This raises `ValidationError` if a linked target doesn't exist, which Django surfaces as a form error.

### 2. View: sync references after save

After the model instance is saved, call `sync_references()` to update the `RecordReference` table:

```python
from flipfix.apps.core.markdown_links import sync_references

# After save:
sync_references(instance, instance.text)
```

**Where to call it depends on the form type:**

- **ModelForm with `save(commit=True)`**: Call in the form's `save()` method:

  ```python
  def save(self, commit=True):
      instance = super().save(commit=commit)
      if commit:
          sync_references(instance, instance.text_field)
      return instance
  ```

- **Regular Form or `save(commit=False)` pattern**: Call in the view after `instance.save()`:
  ```python
  instance.save()
  sync_references(instance, instance.text_field)
  ```

**Important**: Some views use `form.save(commit=False)` then `instance.save()` separately. A form `save()` override with `if commit:` won't trigger in this case — put the `sync_references()` call in the view instead.

### 3. Template: enable the autocomplete UI

Add `data-link-autocomplete` and `data-link-api-url` to the textarea widget:

**In a form class:**

```python
"text": forms.Textarea(attrs={
    "data-link-autocomplete": "",
    "data-link-api-url": "/api/link-targets/",
})
```

**In a template (e.g., `text_card_editable.html` for inline editing):**

```html
<textarea data-link-autocomplete data-link-api-url="{% url 'api-link-targets' %}">
{{ content }}</textarea
>
```

The template must also include the JS:

```html
{% include "core/partials/markdown_textarea_scripts.html" %}
```

### 4. Signal: clean up references on delete

When a source record is deleted, its `RecordReference` rows must be cleaned up. Use the `register_reference_cleanup()` helper in your `AppConfig.ready()` method — it connects `post_delete` signals for each model in a single call:

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    ...

    def ready(self):
        from flipfix.apps.core.models import register_reference_cleanup

        from .models import MyModel, MyOtherModel

        register_reference_cleanup(MyModel, MyOtherModel)
```

Pass every model whose text fields can contain `[[type:ref]]` markdown links (i.e. any model passed to `sync_references`). No separate `signals.py` file is needed.

### 5. Detail view: handle inline text edits (if applicable)

If the detail page uses `text_card_editable.html` for inline AJAX editing, the detail view's POST handler must convert, save, and sync. Use `save_inline_markdown_field()` which handles all three steps:

```python
from flipfix.apps.core.markdown_links import save_inline_markdown_field

if action == "update_text":
    text = request.POST.get("text", "")
    try:
        save_inline_markdown_field(self.object, "text", text)
    except ValidationError as e:
        return JsonResponse({"success": False, "errors": e.messages}, status=400)
    return JsonResponse({"success": True})
```

## Existing Registrations to Copy From

| Scenario                                  | Copy from                                                                         |
| ----------------------------------------- | --------------------------------------------------------------------------------- |
| Simple slug-based type                    | `catalog/apps.py` → `machine` registration                                        |
| Simple ID-based type                      | `maintenance/apps.py` → `problem` registration                                    |
| ID-based with related model in label      | `parts/apps.py` → `partrequestupdate` registration                                |
| Irregular slug format (e.g., `tag/slug`)  | `wiki/apps.py` → `page` registration                                              |
| Scoped link target (filter linkable rows) | `accounts/apps.py` → `user` registration (uses `target_queryset`)                 |
| ModelForm source with `save(commit=True)` | `maintenance/forms.py` → `MaintainerProblemReportForm`                            |
| Regular Form source (sync in view)        | `maintenance/forms.py` → `LogEntryQuickForm` + `maintenance/views/log_entries.py` |
| Signal cleanup                            | `maintenance/apps.py` → `register_reference_cleanup()` call                       |
| Inline AJAX text editing                  | `maintenance/views/log_entries.py` → `LogEntryDetailView.post()`                  |

## RecordReference Model

`RecordReference` in `core/models.py` tracks which records link to which other records, using Django's contenttypes framework for polymorphic source/target relationships.

This powers "what links here" queries (currently used by wiki page delete confirmation to warn about broken links).

The table is kept in sync by `sync_references()` — it diffs current links in the content against existing rows and batch-creates/deletes the difference.

**Important**: `GenericForeignKey` doesn't support `on_delete`, so deleting a target record does not cascade to `RecordReference` rows. Broken links render as `*[broken link]*` in markdown output. This is by design — it lets users see and fix broken links rather than silently losing them.

## API Endpoints

| Endpoint                                      | URL name           | Purpose                                               |
| --------------------------------------------- | ------------------ | ----------------------------------------------------- |
| `GET /api/link-types/`                        | `api-link-types`   | Returns available link types for the `[[` type picker |
| `GET /api/link-targets/?type=machine&q=black` | `api-link-targets` | Returns matching targets for autocomplete search      |

Both require maintainer portal access (`CanAccessMaintainerPortalMixin`).
