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
