# Interactive Markdown Checkboxes

In Flipfix, any markdown field can contain a list of checkboxes. When the markdown is in display mode, you get checkboxes, and checking a box saves the markdown with that item checked.

The markdown looks like this:

```markdown
## Test plan

- [x] Item 1
- [ ] Item 2
```

This works on every markdown field in the system: Wiki Pages, Problems, Log Entries, Part Requests, Part Request Updates.

This allows, for example, you to write a detailed Problem Report containing a checklist, and then check off individual items. When all the items are checked off, you'd then manually close the Problem Report. There's no automatic "close Problem Report when all items are checked off". There's no "prevent Problem Report from being closed if items are unchecked".

## Features

- **Nested lists**. Github handles nested lists, this should too.
- **Enter creates new list item**. When you're in edit mode at the end of a checklist item and hit enter, it creates a new unchecked item on the new row. It's a nice quality of life improvement.
