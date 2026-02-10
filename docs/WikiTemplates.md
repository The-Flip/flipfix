# Wiki Templates

## Overview

Wiki **templates** turn portions of wiki pages into reusable starting points for creating Flipfix records.

For example, a wiki page might document the "Final Checklist Before Going to Floor" — everything a maintainer needs to verify before a machine leaves the workshop. That checklist can pre-fill a problem report in two ways: a button on the wiki page itself, or a template dropdown on the Problem Report create form. Either way, the result is the same: a new record with the checklist already in the description, ready to be worked through with [interactive checkboxes](MarkdownEditing.md#interactive-checkboxes).

There's different templates for different record create scenarios...

- for specific **record types**:
  - New Parts Request -> a parts request order form
  - New Log Entry -> a cleaning checklist
  - New Wiki Page -> New Acquisition Checklist
- for specific **machines**:
  - Gorgar -> New Log Entry -> Checklist for Cleaning Gorgar's Statue
- for specific **machine locations**:
  - Workshop -> Checklist for Graduating To The Game Floor
- for specific **priorities** (showstopper vs task):
  - Problem Report -> Priority: Task -> Cleaning a Machine

Once created, the record has no ongoing connection to the wiki page. It's a one-time snapshot.

## Writing Templates

### Template Format

Templates are defined entirely in wiki page content using HTML comment markers.

A template has two parts: a **content block** (the text to pre-fill) and a **`template:action`** marker (controls where the template appears).

```markdown
<!-- template:start name="floor-checklist" -->

## Final Checklist Before Going to Floor

- [ ] playfield cleaned
- [ ] all lights working
- [ ] coin mech tested

<!-- template:end name="floor-checklist" -->

<!-- template:action name="floor-checklist" action="button,option" type="problem" priority="task" label="Floor Checklist" -->
```

The content between `template:start` and `template:end` renders as normal visible markdown on the wiki page. The `template:action` marker controls how the template reaches users — as a button on the page, an option in create form dropdowns, or both. The `name` attribute links them together.

Multiple templates per page are supported.

### Attributes

Attributes on `template:action`:

| Attribute  | Required | Description                                                                                    |
| ---------- | -------- | ---------------------------------------------------------------------------------------------- |
| `action`   | yes      | How the template reaches users: `button`, `option`, or `button,option`.                        |
| `name`     | yes      | Links the marker to its content block.                                                         |
| `type`     | yes      | Record type: `problem`, `log`, `partrequest`, or `page`.                                       |
| `label`    | yes      | Display text for the button or template selector.                                              |
| `machine`  | no       | Machine slug. Scopes the template to that machine.                                             |
| `location` | no       | Location slug. Scopes the template to machines in that location.                               |
| `priority` | no       | Pre-selects priority (`type="problem"` only): `unplayable`, `major`, `minor`, `task`.          |
| `tags`     | no       | Comma-separated tags for new page (`type="page"` only). `@source` inherits source page's tags. |
| `title`    | no       | Pre-fills the title field (`type="page"` only).                                                |

### Buttons on Wiki Pages

A `<!--template:action action="button" ...-->` renders a clickable button on the wiki page. Clicking the button opens the appropriate create form with the template content pre-filled in the description.

If the template specifies a `machine`, the form opens scoped to that machine. If it specifies a `priority`, that priority is pre-selected.

### Template Selector on Create Forms

A `<!--template:action action="option" ...-->` registers the template in create form dropdowns. When creating a record, a template dropdown appears if any templates match the current context. The dropdown filters based on:

- **Record type** — the kind of record being created (problem report, log entry, etc.)
- **Priority** — the currently selected priority
- **Machine** — the machine the record is for
- **Location** — the location of the machine

Selecting a template populates the description field with the template content.

### Buttons and Options are Independent

The `action` attribute controls how the template reaches users. It accepts `button`, `option`, or `button,option`:

- **`action="button"`** — the template is available from the wiki page but doesn't appear in create form dropdowns.
- **`action="option"`** — the template appears in create form dropdowns but has no button on the wiki page.
- **`action="button,option"`** — the template is available from both places. This is the most common setup.

### How Attributes Control Filtering

For templates with `action="option"` (or `action="button,option"`), attributes control when the template appears in the form's template selector.

**If an attribute is set**, the template only appears when the form's context matches that value. A template with `priority="task"` only appears when the priority dropdown is set to Task.

**If an attribute is omitted**, the template appears regardless of that dimension. A template with no `machine` attribute appears for every machine.

This means:

- `type="problem" priority="task"` — appears on all problem report forms when priority is Task, for any machine.
- `type="problem" machine="blackout"` — appears on Blackout problem report forms at any priority.
- `type="problem" priority="task" machine="blackout"` — appears only on Blackout problem reports with Task priority.
- `type="problem"` — appears on all problem report forms.

If a template isn't showing up where you expect, check that its attributes don't exclude the current context.

### Documenting Templates in Wiki Pages

Template markers inside fenced code blocks are treated as literal text — they are not parsed, validated, or rendered as buttons. This means wiki pages can include example syntax in code fences without the examples being processed:

````markdown
```
<!-- template:start name="example" -->
...checklist content...
<!-- template:end name="example" -->

<!-- template:action name="example" action="button" type="problem" label="Go" -->
```
````

## Architecture

- [WikiTemplateArchitecture.md](WikiTemplateArchitecture.md) — rendering pipeline, pre-fill mechanism, index table, API endpoints
