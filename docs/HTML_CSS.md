# HTML & CSS Development Guide

This is a guide for developers and AI assistants creating HTML and CSS.

Focus on clean, modern, lightweight mobile-first pages that rely only on system fonts and a single cached stylesheet.


## Things to Avoid

- **Do not introduce new font stacks** or load remote fonts. Rely on the font stack defined in the base stylesheet.
- **Do not hardcode colors, spacing, or shadows**. Rely on the CSS variables and tokens established in the base stylesheet.

## Organization

- **Single Stylesheet**. This project uses a single stylesheet, [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Add new classes there with appropriate section comments. This handles 95% of styling needs and keeps CSS cacheable and maintainable.

- **Per-page Styling is a Rare Exception**. For truly one-off page-specific styling that won't be reused elsewhere, a `<style>` block in the template is acceptable. Use sparingly—if the CSS might be useful on other pages or exceeds ~20 lines, add it to styles.css instead.

- **Never Use Inline `style=` Attributes**. Inline styles (`style="..."`) are prohibited.  Always use CSS classes instead.


## Component Expectations

The project establishes component patterns in [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Before creating new components, review existing patterns:
- **Buttons** (`.btn` with modifiers like `.btn-primary`)
- **Badges, Tags, Pills** (`.badge` with status modifiers like `.badge-open`, `.badge-fixing`)
- **Cards** (`.card` with BEM elements like `.card__header`, `.card__body`)
- **Machine Cards** (`.machine-card` with structured BEM elements)
- **Forms** (`.form-field` wrapper pattern)
- **Messages & Alerts** (`.message` with type modifiers)
- **Utility classes** (`.hidden`, `.text-muted`, `.badge-right`)

**Do not introduce new component patterns without documenting them here**.

## CSS Class Naming

This project uses a "BEM-ish" approach to naming CSS classes:

### Use `Block__Element` (double underscore) for component hierarchy
Use `block__element` when creating component subparts (header, body, footer, meta, etc.).  Examples:
- `.machine-card__row` - row is part of machine-card
- `.machine-card__name` - name is part of machine-card
- `.breadcrumb__trail` - trail is part of breadcrumb

### Use `Block-modifier` (single hyphen) for variants/states
Use `block-modifier` when adding variants (colors, sizes, states).  Examples:
- `.badge-open`, `.badge-closed`, `.badge-fixing`
- `.btn-primary`, `.btn-secondary`
- `.breadcrumb-with-actions`

### Don't use hyphens for standalone utilities
Use simple names for standalone utilities (`.card`, `.btn`, `.hidden`)

## Accessibility & Interaction
- Use semantic HTML elements (e.g., `<nav>`, `<main>`, `<section>`, `<table>`).
- Maintain WCAG AA contrast for text/background combinations.
- Do not remove focus outlines without providing explicit `:focus-visible` styles with equal or better visibility.
- Buttons and links should have hover + active states distinct from focus.
- Respect `@media (prefers-reduced-motion: reduce)` by disabling transitions.


## Performance & Build

- Stick to vanilla CSS compiled once (no external fonts, minimal animations).
- Use `@layer base, components, utilities;` to control cascade if desired.
- Gzip production CSS and ensure it is fingerprinted via Django’s `collectstatic`.
