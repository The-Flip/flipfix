# HTML & CSS Development Guide

This is a guide for developers and AI assistants creating HTML and CSS.

Focus on clean, modern, lightweight mobile-friendly pages that rely only on system fonts and a single cached stylesheet.


## Things to Avoid

- **Do not introduce new font stacks** or load remote fonts. Rely on the font stack defined in the base stylesheet.
- **Do not hardcode colors, spacing, or shadows**. Rely on the CSS variables and tokens established in the base stylesheet.

## Organization

- **Single Stylesheet**. This project uses a single stylesheet, [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Add new classes there with appropriate section comments. This handles 95% of styling needs and keeps CSS cacheable and maintainable.

- **Per-page Styling is a Rare Exception**. For truly one-off page-specific styling that won't be reused elsewhere, a `<style>` block in the template is acceptable. Use sparingly—if the CSS might be useful on other pages or exceeds ~20 lines, add it to styles.css instead.

- **Never Use Inline `style=` Attributes**. Inline styles (`style="..."`) are prohibited.  Always use CSS classes instead.


## Component Expectations

The project establishes component patterns in [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Before creating new components, review existing patterns:

### Layout Components
- **Page Header** (`.page-header` with `.page-header__left`, `.page-header__right` for breadcrumbs and actions)
- **List Header** (`.list-header` with `.list-header__left`, `.list-header__right` for search/filters and actions)
- **Section Header** (`.section-header` with `.section-header__actions` for h2 headings with inline actions)

### UI Components
- **Buttons** (`.btn` with modifiers like `.btn-primary`, `.btn-secondary`)
- **Badges, Tags, Pills** (`.badge` with status modifiers like `.badge-open`, `.badge-fixing`, `.badge-inline`)
- **Cards** (`.card` with BEM elements like `.card__header`, `.card__body`)
- **Machine Cards** (`.machine-card` with structured BEM elements)
- **Forms** (`.form-field` wrapper pattern, `.form-inline` for inline forms)
- **Messages & Alerts** (`.message` with type modifiers like `.message--success`, `.message--error`)
- **User Menu** (`.user-menu` with `.user-menu__avatar`, `.user-menu__dropdown`, `.user-menu__item`)

### Interactive Components
- **Inline Edit** (`.inline-edit-group`, `.inline-edit-field`, `.inline-edit-select`)
- **Status Indicator** (`.status-indicator` with modifiers `.saving`, `.saved`, `.error`)
- **Media Grid** (`.media-grid`, `.media-item`, `.media-link`, `.media-video`, `.btn-delete-media`)

### Utility Classes
- `.hidden` - Hide elements (use with JS classList.add/remove for toggling)
- `.text-muted` - Muted text color
- `.form-inline` - Display form inline
- `.badge-inline` - Badge with left margin (for badges inside buttons)
- `.media-thumbnail` - Thumbnail image spacing

**Do not introduce new component patterns without documenting them here**.

## JavaScript Visibility Pattern

When toggling element visibility with JavaScript, use the `.hidden` class instead of `style.display`:

```html
<!-- In template -->
<div id="my-element" class="hidden">...</div>
```

```javascript
// In JavaScript - show element
element.classList.remove('hidden');

// Hide element
element.classList.add('hidden');
```

This keeps styling in CSS and makes the pattern consistent across the codebase.

## CSS Class Naming

This project uses a "BEM-ish" approach to naming CSS classes:

### Use `Block__Element` (double underscore) for component hierarchy
Use `block__element` when creating component subparts (header, body, footer, meta, etc.).  Examples:
- `.machine-card__row` - row is part of machine-card
- `.machine-card__name` - name is part of machine-card
- `.page-header__left` - left section is part of page-header

### Use `Block-modifier` (single hyphen) for variants/states
Use `block-modifier` when adding variants (colors, sizes, states).  Examples:
- `.badge-open`, `.badge-closed`, `.badge-fixing`
- `.btn-primary`, `.btn-secondary`

### Don't use hyphens for standalone utilities
Use simple names for standalone utilities (`.card`, `.btn`, `.hidden`)

## Responsive Design

The site must be optimized for mobile, tablet, and desktop. Breakpoints are defined in the stylesheet.  Avoid tables; hard to make those responsive.

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
