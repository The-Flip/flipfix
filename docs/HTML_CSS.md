# HTML & CSS Development Guide

This guide covers creating HTML and CSS for this project.

Focus on clean, modern, lightweight mobile-friendly pages that rely on a single cached stylesheet.


## Things to Avoid

- **Do not hardcode colors, spacing, or shadows**. Rely on the CSS variables and tokens established in the base stylesheet.

## Organization

- **Single Stylesheet**. This project uses a single stylesheet, [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Add new classes there with appropriate section comments. This handles 95% of styling needs and keeps CSS cacheable and maintainable.

- **Per-page Styling is a Rare Exception**. For truly one-off page-specific styling that won't be reused elsewhere, a `<style>` block in the template is acceptable. Use sparingly—if the CSS might be useful on other pages or exceeds ~20 lines, add it to styles.css instead.

- **Never Use Inline `style=` Attributes**. Inline styles (`style="..."`) are prohibited.  Always use CSS classes instead.


## Page Layout

Most pages extend `layouts/two_column.html`. See that file for available blocks (`breadcrumbs`, `mobile_actions`, `sidebar`, `main`).

For list pages with search and infinite scroll, extend `maintenance/global_list_base.html` instead.

For simple centered pages (like error pages), extend `layouts/minimal_centered.html` which provides a `centered_content` block. Error pages extend `layouts/error.html` which builds on this with a consistent icon/heading/message structure.

## Component Expectations

The project establishes component patterns in [the_flip/static/core/styles.css](../the_flip/static/core/styles.css). Before creating new components, review existing patterns:

### Layout Components
- **Page Header** (`.page-header` with `.page-header__left`, `.page-header__right` for breadcrumbs and actions)
- **List Header** (`.list-header` with `.list-header__left`, `.list-header__right` for search/filters and actions)
- **Section Header** (`.section-header` with `.section-header__actions` for h2 headings with inline actions)
- **Flip Card** (`.flip-card` with `.flip-card__top`, `.flip-card__main`, `.flip-card__bottom` and optional left/right sub-elements for aligning content; use `.flip-card--clickable` when the whole card should be a link, and `.flip-card-list` to reset list spacing when rendering multiple flip-cards)
- **Centered Container** (`.centered-container` - flexbox container that vertically and horizontally centers content)

### UI Components
- **Buttons** (`.btn` with modifiers like `.btn--primary`, `.btn--secondary`, `.btn--log`, `.btn--report`)
- **Badges, Tags, Pills** (`.badge` with status modifiers like `.badge-open`, `.badge-fixing`, `.badge-inline`)
- **Cards** (`.card` with BEM elements like `.card__header`, `.card__body`)
- **Forms** (`.form-field` wrapper pattern, `.form-inline` for inline forms) - See [Forms.md](Forms.md) for form building patterns and components
- **Messages & Alerts** (`.message` with type modifiers like `.message--success`, `.message--error`)
- **User Menu** (`.user-menu` with `.user-menu__avatar`, `.user-menu__dropdown`, `.user-menu__item`)

### Interactive Components
- **Inline Edit** (`.inline-edit-group`, `.inline-edit-field`, `.inline-edit-select`)
- **Status Indicator** (`.status-indicator` with modifiers `.saving`, `.saved`, `.error`)
- **Media Grid** (`.media-grid`, `.media-item`, `.media-link`, `.media-video`, `.btn-delete-media`)

### Utility Classes
- `.hidden` - Hide elements (use with JS classList.add/remove for toggling)
- `.visually-hidden` - Hide visually but keep accessible to screen readers (see [Icon Accessibility](#icon-accessibility))
- `.text-muted` - Muted text color
- `.text-center` - Center-align text
- `.text-xs` - Extra small text
- `.text-sm` - Small text
- `.form-inline` - Display form inline
- `.badge-inline` - Badge with left margin (for badges inside buttons)
- `.media-thumbnail` - Thumbnail image spacing

**Do not introduce new component patterns without documenting them here**.

## JavaScript

See [Javascript.md](Javascript.md) for JavaScript patterns and component documentation.

## CSS Class Naming

This project uses a "BEM-ish" approach to naming CSS classes:

### Use `Block__Element` (double underscore) for component hierarchy
Use `block__element` when creating component subparts (header, body, footer, meta, etc.). Examples:
- `.flip-card__top` - top section of flip-card
- `.flip-card__bottom-right` - right-aligned bottom content of flip-card
- `.page-header__left` - left section of page-header

### Use `Block--modifier` (double hyphen) for variants/states
Use `block--modifier` when adding variants (colors, sizes, states).  Examples:
- `.btn--primary`, `.btn--secondary`, `.btn--log`
- `.pill--neutral`, `.pill--status-good`, `.pill--status-broken`

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

### Icon Accessibility

Decorative icons (icons with adjacent text labels) must include `aria-hidden="true"` to prevent screen readers from announcing redundant information:

```html
<button><i class="fa-solid fa-check" aria-hidden="true"></i> Save</button>
```

For icons that convey meaning without adjacent text, provide screen reader text using the `.visually-hidden` class:

```html
<span><i class="fa-solid fa-bug" aria-hidden="true"></i><span class="visually-hidden">Problem</span> #123</span>
```


## XSS Protection

Django auto-escapes `{{ variable }}` output. User-submitted text is safe to display.

Only use `{{ variable|safe }}` for HTML you control (e.g., markdown rendered server-side).

## Performance & Build

- Stick to vanilla CSS compiled once (no external fonts, minimal animations).
- Use `@layer base, components, utilities;` to control cascade if desired.
- Gzip production CSS and ensure it is fingerprinted via Django's `collectstatic`.
