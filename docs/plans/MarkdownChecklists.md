# Interactive Markdown Checkboxes

## Problem Statement

You know how Github Issues allow markdown, and that markdown can contain a list of checkboxes? When the markdown is in display mode, you get checkboxes, and checking a box saves the markdown with that item checked.

The markdown looks like this:

```markdown
## Test plan

- [x] Item 1
- [ ] Item 2
```

We want the same thing for Flipfix's existing markdown support. That means the markdown on Problems, Log Entries, Part Requests, Part Request Updates.

This will, for example, allow people to write a detailed Problem Report containing a checklist, and then check off individual items. When all the items are checked off, they'd then manually close the Problem Report. There's no automatic "close Problem Report when all items are checked off". There's no "prevent Problem Report from being closed if items are unchecked".

## Features

- **Nested lists**. Github handles nested lists, this should too.
- **Enter creates new list item**. When I'm in edit mode at the end of a checklist item and hit enter, it creates a new unchecked item on the new row. Github does this, it's a nice quality of life improvement.

## Approaches Considered

We evaluated whether or not to use a markdown extension or just some custom post-processing code.

We decided on the post-processing approach. It's simpler and more secure, because the `<input>`elements are never part of user-authored content that passes through HTML sanitization.

### Approach: Custom Post-Processing

Don't use any new markdown extensions. Leverage the fact that Python's markdown library already preserves `- [ ] and - [x]` as literal text inside `<li>` tags (e.g., `<li>[ ] item</li>)`. This text passes through `nh3`, the HTML santizer this project uses, unchanged. After sanitization, use regex post-processing to replace these markers with `<input type="checkbox">` elements. Since the `<input>` tags are injected by trusted server code after sanitization, they never pass through `nh3` — no changes to the security model are needed.

### Approach: The `pymdownx.tasklist` Markdown Extension

This is the main tasklist extension. From pymdown-extensions package. MIT licensed. Actively maintained: latest version 10.20.1 (Jan 2026). Generates proper semantic HTML with task-list and task-list-item CSS classes.

#### What `pymdownx.tasklist` generates

```html
<ul class="task-list">
  <li class="task-list-item">
    <input type="checkbox" disabled="" checked="" />
    item 1
  </li>
</ul>
```

#### Con: This adds a lot of weight

It adds `pymdown-extensions`, a 269KB wheel with ~20 other extensions we don't use.

#### Con: HTML sanitizer issues with using `pymdownx.tasklist`

Even if we add the extension, the `nh3` HTML santizer this project uses would strip the `<input>` tags it generates, because input is not in our ALLOWED_TAGS. So we'd need to either:

- **Add input to ALLOWED_TAGS** -- but nh3 doesn't support filtering by attribute values, so we can't restrict to just type="checkbox". Any user could then inject `<input type="text">`, `<input type="password">`, etc. into their markdown. However, this is not a huge issue because we don't allow name/form attributes.
- **Token-swap around nh3** -- replace `<input>` with placeholder tokens before nh3, restore after. Fragile and ugly.

If we use pymdownx.tasklist + allow `<input>` through nh3, we'd need to also allow the `type`, `checked`, and `disabled` attributes on input — and we'd need our JS to `add data-checkbox-index` attributes client-side (since `nh3` would strip custom `data-` attributes from the extension's output).

The post-processing approach avoids all of that by injecting the complete `<input>` element with all needed attributes in one step.

#### Con: This doesn't simplify our task

This extension doesn't actually simplify things -- it just shifts where the `<input>` tags originate, and we'd still need to deal with nh3 stripping them.

The one thing the extension gives us is the task-list class on the parent `<ul>`, which is nice for CSS targeting. But we can add that in our post-processing too if needed.
