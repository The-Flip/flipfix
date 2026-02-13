# Template Tags Guide

This guide documents the organization of Django template tag libraries in this project.

## Organization Principles

Template tags are split across multiple focused libraries rather than a single monolithic file. Each library has a clear organizing principle:

1. **Core libraries** live in `core/templatetags/` and contain shared, domain-agnostic components
2. **App libraries** live in `<app>/templatetags/` and contain domain-specific display logic
3. **Form libraries** use the `<app>_form_tags` naming convention to separate form components from display tags

When adding a new template tag, use the "where does this go?" test:

- Does it render a model's status/data? → That model's app `<app>_tags.py`
- Is it a form component for a specific domain? → That domain's `<app>_form_tags.py`
- Is it a generic UI primitive (icon, pill, date)? → `ui_tags.py`
- Is it about page layout (sidebars)? → `sidebar_tags.py`
- Is it about rendering collections (lists, timelines)? → `list_tags.py`
- Is it generic form infrastructure? → `form_tags.py`
- Is it about markdown? → `markdown_tags.py`
- Is it about video/media? → `video_tags.py`

## Library Reference

### Core Libraries

These live in `the_flip/apps/core/templatetags/` and are loaded as `{% load <name> %}`.

#### `ui_tags` — Atomic UI primitives

No domain knowledge. Used on every page type.

| Component    | Type          | Description                                                                   |
| ------------ | ------------- | ----------------------------------------------------------------------------- |
| `icon`       | Simple tag    | Font Awesome icon with auto `aria-hidden`. Options: `class`, `label`, `style` |
| `pill`       | Inclusion tag | Status pill/badge with variant styling                                        |
| `smart_date` | Filter        | Render timestamp as `<time>` element for JS formatting                        |
| `month_name` | Filter        | Convert month number (1-12) to name                                           |
| `addstr`     | Filter        | Concatenate two values as strings                                             |

Also exports `_settable_pill_context()`, a helper function used by app-level settable pill tags.

#### `video_tags` — Video/media components

| Component         | Type          | Description                                |
| ----------------- | ------------- | ------------------------------------------ |
| `video_player`    | Inclusion tag | Video player with transcode state handling |
| `video_thumbnail` | Inclusion tag | Video thumbnail for list views             |

#### `sidebar_tags` — Sidebar page structure

| Component               | Type      | Description                                                      |
| ----------------------- | --------- | ---------------------------------------------------------------- |
| `sidebar_section`       | Block tag | `{% sidebar_section label="Stats" %}...{% endsidebar_section %}` |
| `editable_sidebar_card` | Block tag | Sidebar card with edit dropdown                                  |

#### `list_tags` — List/collection components

| Component           | Type          | Description                           |
| ------------------- | ------------- | ------------------------------------- |
| `stat_grid`         | Inclusion tag | Grid of statistics                    |
| `empty_state`       | Inclusion tag | Empty/no results message              |
| `child_list_search` | Inclusion tag | Search input for child item lists     |
| `timeline`          | Block tag     | Timeline container with vertical line |
| `timeline_entry`    | Block tag     | Timeline entry with icon              |

#### `form_tags` — Generic form infrastructure

| Component               | Type          | Description                                        |
| ----------------------- | ------------- | -------------------------------------------------- |
| `form_field`            | Inclusion tag | Renders field with label, input, help text, errors |
| `form_fields`           | Inclusion tag | Renders all visible fields in a form               |
| `form_label`            | Simple tag    | Label with "(optional)" for non-required fields    |
| `form_non_field_errors` | Inclusion tag | Renders non-field errors                           |
| `field_errors`          | Inclusion tag | Renders field errors only                          |
| `field_help_text`       | Inclusion tag | Renders field help text only                       |
| `getfield`              | Filter        | Get form field by name                             |

See [`Forms.md`](Forms.md) for form building patterns.

#### `markdown_tags` — Markdown pipeline

| Component              | Type   | Description                                                             |
| ---------------------- | ------ | ----------------------------------------------------------------------- |
| `render_markdown`      | Filter | Convert markdown to sanitized HTML with auto-linked URLs and wiki links |
| `storage_to_authoring` | Filter | Convert storage-format links to authoring format for editing            |

### App Libraries

These live in each app's `templatetags/` directory.

#### `catalog_tags` — Machine display (`catalog/templatetags/`)

| Component                        | Type          | Description                              |
| -------------------------------- | ------------- | ---------------------------------------- |
| `settable_machine_status_pill`   | Inclusion tag | Clickable status dropdown for machines   |
| `settable_machine_location_pill` | Inclusion tag | Clickable location dropdown for machines |
| `machine_status_css_class`       | Filter        | Pill CSS class for machine status        |
| `machine_status_icon`            | Filter        | Font Awesome icon for machine status     |
| `machine_status_btn_class`       | Filter        | Button CSS class for machine status      |
| `manufacturer_year`              | Filter        | "Manufacturer · Year" string             |

#### `maintenance_tags` — Problem/log display (`maintenance/templatetags/`)

| Component                        | Type          | Description                                      |
| -------------------------------- | ------------- | ------------------------------------------------ |
| `settable_problem_status_pill`   | Inclusion tag | Clickable status dropdown for problem reports    |
| `settable_problem_priority_pill` | Inclusion tag | Clickable priority dropdown (excludes Untriaged) |
| `problem_report_status_pill`     | Inclusion tag | Read-only status pill                            |
| `problem_report_type_pill`       | Inclusion tag | Read-only problem type pill                      |
| `problem_report_priority_pill`   | Inclusion tag | Read-only priority pill                          |
| `problem_report_summary`         | Filter        | Concise summary: type + description              |
| `problem_report_meta`            | Filter        | Reporter name + timestamp                        |
| `log_entry_meta`                 | Filter        | Maintainer names + timestamp                     |
| `problem_status_css_class`       | Filter        | Pill CSS class for problem status                |
| `problem_status_icon`            | Filter        | Icon for problem status                          |
| `problem_priority_css_class`     | Filter        | Pill CSS class for problem priority              |
| `problem_priority_icon`          | Filter        | Icon for problem priority                        |

#### `parts_tags` — Parts display (`parts/templatetags/`)

| Component                           | Type          | Description                                 |
| ----------------------------------- | ------------- | ------------------------------------------- |
| `settable_part_request_status_pill` | Inclusion tag | Clickable status dropdown for part requests |

#### `accounts_tags` — User display (`accounts/templatetags/`)

| Component                    | Type   | Description                                |
| ---------------------------- | ------ | ------------------------------------------ |
| `display_name_with_username` | Filter | "First Last (username)" or just "username" |

#### `accounts_form_tags` — Maintainer form components (`accounts/templatetags/`)

| Component                       | Type          | Description                                      |
| ------------------------------- | ------------- | ------------------------------------------------ |
| `maintainer_autocomplete_field` | Inclusion tag | Autocomplete input for user search               |
| `maintainer_chip_input_field`   | Inclusion tag | Multi-select chip input for maintainer selection |

#### `wiki_form_tags` — Wiki form components (`wiki/templatetags/`)

| Component                 | Type          | Description                         |
| ------------------------- | ------------- | ----------------------------------- |
| `template_selector_field` | Inclusion tag | Template dropdown on create forms   |
| `tag_chip_input_field`    | Inclusion tag | Chip-based tag input for wiki pages |

## Pill Variants

- `neutral` (default), `open`, `closed`, `status-fixing`, `status-good`, `status-broken`
- `open` and `closed` are semantic aliases (open=broken styling, closed=good styling)
- `priority-untriaged` (warning/orange), `priority-unplayable` (red), `priority-major` (darker orange). Minor and Task use `neutral`.

## Creating New Components

1. Determine which library the tag belongs to (see organizing principles above)
2. Add function to the appropriate `templatetags/<library>.py` file
3. For inclusion tags, create template in `templates/components/`
4. Document in this file and update the component table in `AGENTS.src.md`

## Template Load Pattern

Templates load only the libraries they need. A typical detail page:

```html
{% load static %} {% load ui_tags %} {% load sidebar_tags %} {% load maintenance_tags %}
```

This makes each template's dependencies explicit and scannable.
