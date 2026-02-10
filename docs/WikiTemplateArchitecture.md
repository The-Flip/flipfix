# Wiki Template Architecture

For what templates are and how to write them, see [WikiTemplates.md](WikiTemplates.md).

## Marker syntax

Templates are defined with HTML comment markers:

- `<!-- template:start name="..." -->` TEMPLATE CONTENT GOES HERE `<!-- template:end name="..." -->` — delimit the content block
- `<!-- template:action name="..." action="..." type="..." ... -->` — controls how the template reaches users

The `action` attribute on `template:action` determines delivery:

| Value           | Effect                                                      |
| --------------- | ----------------------------------------------------------- |
| `button`        | Renders a button on the wiki page                           |
| `option`        | Registers in create-form template dropdowns                 |
| `button,option` | Both: button on wiki page + option in create-form dropdowns |

## Rendering on the wiki page

When `action` contains "button", the wiki page displays a button wherever `template:action` is placed.

The content between start/end markers renders as normal visible markdown. The `template:action` marker is replaced with a styled button wherever it appears on the page.

**Challenge**: HTML comments are stripped by nh3 (the HTML sanitizer). **Solution**: Token substitution — replace `template:start` and `template:end` with empty string, replace `template:action` (when `action` contains "button") with a unique alphanumeric token before the markdown pipeline, then replace the token with button HTML after sanitization.

The button is a plain `<a>` link to a wiki endpoint:

- `/wiki/actions/<page_pk>/<action_name>/`

## Pre-filling flow (buttons)

```
Click button → GET /wiki/actions/<page_pk>/<action_name>/
  → wiki view loads page, extracts content block
  → converts storage→authoring format links
  → stores in request.session["form_prefill"]
  → 302 redirects to appropriate create URL
  → create view's get_initial() pops session, pre-fills form
```

**Key principle**: create views have zero wiki knowledge. They use a generic `FormPrefillMixin` that checks the session for pre-fill data. The wiki endpoint handles all wiki-specific logic (page loading, content extraction, URL routing). If the page or action block is missing, the endpoint returns 404 (stale link).

## Template option index (dropdowns)

When `action` contains "option", the template is registered in the `TemplateOptionIndex` table whenever the wiki page is saved. This denormalized index stores metadata from the marker (record type, machine, location, priority, label) for fast querying by create forms.

### Sync lifecycle

`sync_template_option_index(page)` is called from two save paths:

1. **Full form save** — `WikiPageForm.save()` calls it after `sync_references()`
2. **Inline AJAX edit** — `WikiPageDetailView.post()` calls it after `save_inline_markdown_field()`

Both paths surface a toast to the author when templates are registered or changed, with links to the affected create forms.

The sync uses a simple delete-then-recreate strategy (options per page are few). It returns a `TemplateSyncResult` with registered/removed counts for the toast.

### API endpoints

Two JSON endpoints serve the create-form template selector:

- `GET /api/wiki/templates/?record_type=...&priority=...&machine_slug=...&location_slug=...` — list matching templates. Query logic uses "any" matching: a template with blank `machine_slug` matches all machines, while one with a specific slug only matches that machine (and vice versa for location and priority).
- `GET /api/wiki/templates/<page_pk>/<template_name>/content/` — fetch the template content in authoring format. For `type="page"` templates, also returns `tags` and `title`.

### JavaScript

`template_selector.js` auto-initializes on `[data-template-selector]` containers. It fetches matching templates from the list API, renders a `<select>` dropdown, and populates the form's textarea on selection. It listens for `machine:changed` events and priority `<select>` changes to refetch. After the user edits the textarea, the selector locks to prevent accidental replacement.

## `type="page"` — creating wiki pages from templates

When `type="page"`, the prefill endpoint redirects to the wiki page create form instead of a maintenance record. The content block pre-fills the new page's content field. Optional `tags` and `title` attributes are stored in separate session keys (`form_prefill_tags`, `form_prefill_title`) and popped by `WikiPageCreateView`.

The special tag value `@source` is resolved at prefill time to the source page's actual tags, so new pages land in the same nav location as the template page. Explicit tags and `@source` can be mixed (e.g., `tags="@source,archive"`); duplicates are removed while preserving order.
