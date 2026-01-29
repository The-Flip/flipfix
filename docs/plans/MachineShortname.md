# Plan: Add `short_name` Field to MachineInstance

## Overview

Add an optional `short_name` field to `MachineInstance` for human-curated abbreviations like:

- "Eight Ball Deluxe Limited Edition" → "Eight Ball"
- "The Getaway: High Speed II" → "Getaway"
- "The Incredible Hulk" → "Hulk"

This enables shorter display in space-constrained contexts and shorter URLs.

---

## Potential Use Cases

| Use Case                    | Current Problem                                       | With `short_name`          |
| --------------------------- | ----------------------------------------------------- | -------------------------- |
| **Mobile breadcrumbs**      | Long breadcrumbs overflow or wrap awkwardly on mobile | Fits comfortably           |
| **In-app system messages**  | Long names in flash messages, confirmations           | Compact messages           |
| **Discord notifications**   | "⚠️ Problem on Eight Ball Deluxe Limited Edition"     | "⚠️ Problem on Eight Ball" |
| **URLs**                    | `/machines/eight-ball-deluxe-limited-edition/`        | `/machines/eight-ball/`    |
| **Autocomplete dropdowns**  | Long names overflow dropdown                          | Fits dropdown width        |
| **Sidebar cards**           | Name overflows sidebar                                | Fits sidebar width         |
| **Machine list cards**      | Card titles overflow                                  | Fits in card layout        |
| **Timeline entries**        | Long names in activity feed                           | Compact timeline           |
| **Problem report grouping** | Section headers in dropdowns overflow                 | Fits dropdown              |
| **QR code labels**          | Text too long for printed labels                      | Fits on labels             |
| **Admin list views**        | Table columns too wide                                | Readable tables            |
| **Parts request UI**        | Machine reference overflows                           | Fits sidebar               |

---

### PR 1: Add `short_name` Field + Admin

**Model changes:**

```python
# the_flip/apps/catalog/models.py

# NEW FIELD
short_name = models.CharField(
    max_length=30,
    blank=True,
    unique=True,  # Must be unique so notifications are unambiguous
    null=True,    # Allow blank (null needed for unique + blank)
    help_text="Short unique name for notifications and mobile display (e.g., 'Eight Ball 2')"
)

# NEW PROPERTY
@property
def short_display_name(self):
    """Return short_name if set, otherwise display_name."""
    return self.short_name or self.display_name

# UPDATE save() to also handle short_name
def save(self, *args, **kwargs):
    if self.name_override == '':
        self.name_override = None
    if self.short_name == '':
        self.short_name = None
    super().save(*args, **kwargs)
```

**Relationship between name fields:**

| Field                | Purpose                                 | Unique?            | Example                                |
| -------------------- | --------------------------------------- | ------------------ | -------------------------------------- |
| `model.name`         | Official model name                     | Yes (among models) | "Eight Ball Deluxe Limited Edition"    |
| `name_override`      | Full custom instance name               | **Yes** (PR 0)     | "Eight Ball Deluxe Limited Edition #2" |
| `short_name`         | Compact identifier                      | **Yes**            | "Eight Ball 2"                         |
| `display_name`       | Property: `name_override or model.name` | —                  | (computed)                             |
| `short_display_name` | Property: `short_name or display_name`  | —                  | (computed)                             |

Note: Multiple `MachineInstance` records can share the same `model` (e.g., two Godzilla machines), which is why `name_override` exists to disambiguate them.

**Admin:** Add `short_name` to the machine admin form:

- Place after `name_override` in field ordering
- Include in list display and search fields
- Help text already on model field

**Model validation:** Add `clean()` method to provide friendly error messages for duplicate values (instead of 500 from `IntegrityError`). Also strip whitespace.

**Files:**

- `docs/plans/MachineShortname.md` — Copy this plan verbatim
- `the_flip/apps/catalog/models.py` — Add field, property, `save()`, `clean()`
- `the_flip/apps/catalog/admin.py` — Add `short_name` to form, list display, search
- `the_flip/apps/catalog/tests.py` — Add tests

**Tests:**

- Machine with no `short_name` → `short_display_name` returns `display_name`
- Machine with `short_name` → `short_display_name` returns `short_name`
- Duplicate `short_name` → `ValidationError` from `clean()` (friendly message)
- Empty string `short_name` → converted to NULL on save
- Multiple machines with NULL `short_name` → allowed
- Whitespace-only `short_name` → converted to NULL

---

## Edge Cases

| Edge Case                                             | Behavior                                                                                          |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `short_name` not set                                  | Fall back to `display_name`                                                                       |
| `short_name` same as `display_name`                   | Valid, no harm                                                                                    |
| Very short (e.g., "BB")                               | Allowed — user's choice                                                                           |
| `short_name` longer than `display_name`               | Allowed — unusual but harmless                                                                    |
| Duplicate `short_name`                                | **Validation error** — must be unique                                                             |
| `short_name` matches another machine's `display_name` | Allowed — only `short_name` values must be unique among themselves                                |
| Sorting/filtering by `short_display_name`             | Not supported — it's a property, not a DB field. Use `Coalesce()` annotation if needed in future. |

---

### PR 2: Mobile Breadcrumbs + CSS

**Approach:**

- Add CSS class `.breadcrumb--hide-mobile` to hide intermediate segments on mobile
- Add CSS class `.breadcrumb--truncate` with `text-overflow: ellipsis` for long names
- Use `short_display_name` for machine name display
- Use Font Awesome icons (not emoji) with `aria-hidden="true"` for accessibility

**Breadcrumb changes:**

| Page                      | Desktop                                       | Mobile                 |
| ------------------------- | --------------------------------------------- | ---------------------- |
| Problem Report            | Machines / [Machine] / Problems / [bug] #N    | [Machine] / [bug] #N   |
| Log Entry (under problem) | Machines / [Machine] / Problem #N / Log Entry | [bug] #N / Log Entry   |
| Log Entry (standalone)    | Machines / [Machine] / Logs / Log Entry       | [Machine] / Log Entry  |
| New Problem Report        | Machines / [Machine] / Problems / New Report  | [Machine] / New Report |
| New Log (from problem)    | Machines / [Machine] / Problem #N / Log Work  | [bug] #N / Log Work    |
| Machine Edit              | Machines / [Machine] / Edit                   | [Machine] / Edit       |

Note: `[bug]` = `<i class="fa-solid fa-bug" aria-hidden="true"></i>` with adjacent text label for screen readers.

**Space budget (375px viewport — iPhone 13 mini/SE):**

- Available width: ~343px (after page padding)
- Worst case: `[Machine] / [bug] #123 / Log Entry` = 3 segments
- Space for machine name: ~165px ≈ **23 characters**
- "Eight Ball" (10 chars) fits; "Eight Ball Deluxe Limited Edition" (34 chars) needs CSS truncation fallback

**Files:**

- `the_flip/static/core/styles.css` — Add breadcrumb mobile classes
- `templates/maintenance/problem_report_detail.html`
- `templates/maintenance/log_entry_detail.html`
- `templates/maintenance/problem_report_form_base.html`
- `templates/maintenance/log_entry_new.html`
- `templates/catalog/machine_edit.html`
- `templates/catalog/machine_model_edit.html`
- `templates/maintenance/machine_qr.html`

**Tests:**

- Visual inspection: breadcrumbs truncate on mobile viewport
- Desktop: full names shown

---

### PR 3: Flash Messages + Discord

**In-app flash messages:**

Use `short_display_name` in Django flash messages where machine names appear:

- `maintenance/views/problem_reports.py:375-376` — "moved from {machine} to {machine}"
- `maintenance/views/log_entries.py:476` — "linked to problem on {machine}"
- `maintenance/views/log_entries.py:514` — "moved from {machine} to {machine}"
- `maintenance/views/log_entries.py:568-573` — "moved from {machine} to {machine}"

**JS-generated messages** (`core.js:267,289,292`) scrape name from `.sidebar__title` — these will continue using full names (consistent with sidebar display).

**Discord notifications:**

Use `short_display_name` in `discord/formatters.py`:

- Problem report titles
- Log entry titles
- Machine status change alerts

**Files:**

- `the_flip/apps/maintenance/views/problem_reports.py`
- `the_flip/apps/maintenance/views/log_entries.py`
- `the_flip/apps/discord/formatters.py`

**Tests:**

- Flash message on machine with `short_name` → uses short name
- Flash message on machine without `short_name` → uses full name
- Discord notification uses `short_display_name`

---

## Deferred to Future PRs

| Use Case                 | Why Defer                  |
| ------------------------ | -------------------------- |
| **Short URLs**           | See analysis below         |
| **Autocomplete display** | Nice-to-have, not urgent   |
| **Sidebar cards**        | Works fine with truncation |
| **Timeline entries**     | Works fine currently       |

### Why Short URLs Are More Complex

Currently, `slug` is auto-generated from `display_name` on first save (see `catalog/models.py:277-286`):

```python
def save(self, *args, **kwargs):
    if not self.slug:
        base_slug = slugify(self.display_name) or "machine"
        # ... uniqueness check with counter
        self.slug = slug
```

To use `short_name` for URLs, we'd need to:

1. **Change slug generation** to prefer `short_name` when set
2. **Handle existing machines** — their slugs are already generated from long names
3. **Redirects** — old URLs (`/machines/eight-ball-deluxe-limited-edition/`) should 301 redirect to new (`/machines/eight-ball/`)
4. **Uniqueness** — what if two machines have the same `short_name`? Currently slugs get `-2`, `-3` suffixes
5. **Slug updates** — if `short_name` changes, should slug change? (breaks bookmarks)

**Options:**

- **A) Don't change slugs at all** — `short_name` is display-only, URLs stay long (simplest)
- **B) Allow manual slug override** — add a `slug_override` field, let admin set short slugs manually
- **C) Auto-regenerate slugs** — complex migration with redirect table

Recommend **Option A for this PR**, then **Option B in a follow-up** if short URLs are important.
