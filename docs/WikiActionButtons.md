# Creating Records From the Wiki

## Overview

You can stick buttons on FlipFix wiki pages that take a portion of the wiki page and create a Flipfix record with it.

For example you might want to stick a button on the [NewMachineIntakeChecklist.md](NewMachineIntakeChecklist.md) that says something like "Start Intake". When you click it, it opens the Create Problem Report form, prepopulated with the name of that machine and the checklist portion of the page as the Problem Report's Description.

- This pairs nicely with the [interactive checkboxes](MarkdownEditing.md#interactive-checkboxes), so you can check off items.
- Once the record is created, there's no further connection with the wiki content. It's a one-time snapshot.

## Syntax

```markdown
<!-- action:start name="intake" -->

## Checklist

- [ ] legs and leg bolts
- [ ] main cabinet condition
      ...

<!-- action:end name="intake" -->

Some other text...

<!-- action:button name="intake" type="problem" label="Start Intake" -->
```

**Attributes** on `action:button`:

| Attribute  | Required | Description                                                                                       |
| ---------- | -------- | ------------------------------------------------------------------------------------------------- |
| `name`     | required | Identifier linking it to start/end                                                                |
| `type`     | required | `problem`, `log`, `partrequest`, or `page`                                                        |
| `label`    | required | Button text                                                                                       |
| `machine`  | optional | Machine slug to pre-select (not used for `type="page"`)                                           |
| `priority` | optional | Pre-select priority (`type="problem"` only). Values: `unplayable`, `major`, `minor`, `task`.      |
| `tags`     | optional | Comma-separated tags for new page (`type="page"` only). `@source` resolves to source page's tags. |
| `title`    | optional | Pre-fill the title field (`type="page"` only)                                                     |

Multiple named action blocks per page are supported.

## Architecture

### Rendering on the wiki page

The wiki page displays a button wherever `action:button` is placed.

The content between start/end markers renders as normal visible markdown. The `action:button` marker is replaced with a styled button wherever it appears on the page.

**Challenge**: HTML comments are stripped by nh3 (the HTML sanitizer). **Solution**: Token substitution — replace `action:start` and `action:end` with empty string, replace `action:button` with a unique alphanumeric token before the markdown pipeline, then replace the token with button HTML after sanitization.

The button is a plain `<a>` link to a wiki endpoint:

- `/wiki/actions/<page_pk>/<action_name>/`

### Pre-filling flow

```
Click button → GET /wiki/actions/<page_pk>/<action_name>/
  → wiki view loads page, extracts content block
  → converts storage→authoring format links
  → stores in request.session["form_prefill"]
  → 302 redirects to appropriate create URL
  → create view's get_initial() pops session, pre-fills form
```

**Key principle**: create views have zero wiki knowledge. They use a generic `FormPrefillMixin` that checks the session for pre-fill data. The wiki endpoint handles all wiki-specific logic (page loading, content extraction, URL routing). If the page or action block is missing, the endpoint returns 404 (stale link).

### `type="page"` — creating wiki pages from templates

When `type="page"`, the prefill endpoint redirects to the wiki page create form instead of a maintenance record. The content block pre-fills the new page's content field. Optional `tags` and `title` attributes are stored in separate session keys (`form_prefill_tags`, `form_prefill_title`) and popped by `WikiPageCreateView`.

The special tag value `@source` is resolved at prefill time to the source page's actual tags, so new pages land in the same nav location as the template page. Explicit tags and `@source` can be mixed (e.g., `tags="@source,archive"`); duplicates are removed while preserving order.
