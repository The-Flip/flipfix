# Markdown Editing

Flipfix enhances textareas that contain markdown with various editing shortcuts and interactive features.

These work on every markdown field in the system: Wiki Pages, Problems, Log Entries, Part Requests, Part Request Updates.

## Link Autocomplete

Type `[[` to get an autocomplete UI to link to any record in the system: Wiki Docs, Problems, Log Entries, etc.

This creates markdown like:

```
[[machine:attack-from-mars]]
```

When rendered, it turns into a clickable URL to that record.

See [MarkdownLinks.md](MarkdownLinks.md) for more details.

## Interactive Checkboxes

When markdown containing task lists is rendered in display mode, checkboxes become interactive. Clicking a checkbox saves the updated markdown via AJAX.

```markdown
- [x] Item 1
- [ ] Item 2
```

This allows you to write, for example, a Problem Report containing a checklist, then check off individual items. When all items are checked off, you'd manually close the Problem Report. There's no automatic close or prevention logic tied to checkbox state.

## Smart Character Wrapping

Select some text then type a wrapping character to wrap instead of replace. For example, select `hello` and type `*` to get `*hello*`.

| Key     | Markdown Meaning     |
| ------- | -------------------- |
| `` ` `` | `Inline code`        |
| `_`     | _Italic_             |
| `*`     | _Italic_ (alternate) |
| `**`    | **Bold**             |

Wrapping preserves the selection, so you can stack: select text, type `*`, type `*` again to get `**bold**`.

## Keyboard Shortcuts

| Shortcut     | Action   | How it works                                                 |
| ------------ | -------- | ------------------------------------------------------------ |
| `Cmd/Ctrl+B` | **Bold** | Toggles `**` around selection or inserts with cursor between |
| `Cmd/Ctrl+I` | _Italic_ | Toggles `*` around selection or inserts with cursor between  |
| `Cmd/Ctrl+K` | Link     | Wraps selection as `[selection](url)` with "url" selected    |

Bold and italic are toggles: if the selection is already wrapped, the shortcut unwraps it.

## Paste URL on Selection

Select some text, then paste a URL starting with `http://` or `https://` from your clipboard. Instead of replacing the text, it wraps it as a markdown link: `[selected text](pasted-url)`.

## Adding Images (Docs only)

In the Docs editor you can add images three ways: paste one (e.g. a screenshot), drag one onto the text box, or use the **Add image** button below it.

- While an image uploads, a placeholder like `![Uploading photo.jpg…](uploading-…)` holds its place on a new line after the cursor's line. When the upload finishes it becomes `![photo](/wiki/media/42/)` with the alt text selected, so you can type a description over it.
- If the upload fails, the placeholder is removed and an error appears at the top of the page.
- Saving is blocked, with a message, until every upload has finished.
- Images up to 25MB; HEIC photos are converted to JPEG. Videos aren't supported yet.
- The detail page's inline editor doesn't offer uploads, but image lines pasted there still work.

How the files are stored and cleaned up is described under `WikiMedia` in [Datamodel.md](Datamodel.md). To offer uploads on another form, see [Forms.md](Forms.md#inline-image-uploads).

## List Enter Continuation

When the cursor is on a list item and you press Enter, it creates the next list item:

- Supports all list markers: `-`, `*`, `+`, and numbered (`1.`, `2.`, etc.)
- **Task lists**: a new unchecked `- [ ]` item is created
- Works with nested lists
- Works inside blockquote prefixes (`>`)
- If the current item is empty, pressing `Enter` removes the prefix instead
- Splits text correctly when the cursor is mid-line

## Tab Indentation

Select some lines of text and hit tab to indent all the lines.

| Key         | Action                                         |
| ----------- | ---------------------------------------------- |
| `Tab`       | Insert 2 spaces (or indent all selected lines) |
| `Shift+Tab` | Remove up to 2 leading spaces per line         |
