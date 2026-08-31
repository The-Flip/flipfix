# HTML & CSS Development Guide

This guide covers creating HTML and CSS for this project.

Focus on clean, modern, lightweight mobile-friendly pages that rely on a single cached stylesheet.

## Things to Avoid

- **Do not hardcode colors, spacing, or shadows**. Rely on the CSS variables and tokens established in the base stylesheet.

## Organization

- **Single Stylesheet**. This project uses a single stylesheet, [flipfix/static/core/styles.css](../flipfix/static/core/styles.css). Add new classes there with appropriate section comments. This handles 95% of styling needs and keeps CSS cacheable and maintainable.

- **Per-page Styling is a Rare Exception**. For truly one-off page-specific styling that won't be reused elsewhere, a `<style>` block in the template is acceptable. Use sparingly—if the CSS might be useful on other pages or exceeds ~20 lines, add it to styles.css instead.

- **Never Use Inline `style=` Attributes**. Inline styles (`style="..."`) are prohibited. Always use CSS classes instead.

## Page Layout

### Base Templates

The project uses a three-level base template hierarchy:

| Template                   | Extends                  | Use For                                                                           |
| -------------------------- | ------------------------ | --------------------------------------------------------------------------------- |
| `base_minimal.html`        | —                        | HTML shell with `<head>` resources (fonts, CSS, favicon). No scripts, no chrome.  |
| `base_minimal_auth.html`   | `base_minimal.html`      | Adds `core.js` (dropdowns, smart dates). For authenticated pages without app nav. |
| `base.html`                | `base_minimal_auth.html` | Full app chrome: header, nav, messages. Most pages use this via layouts.          |
| `base_public_minimal.html` | `base_minimal.html`      | Public pages with logo header and footer. No `core.js`.                           |

Most pages don't extend these directly — use the layout templates below instead.

### Layout Templates

Most pages extend `layouts/two_column.html`. See that file for available blocks (`breadcrumbs`, `breadcrumb_actions`, `two_column_modifier`, `sidebar`, `main`).

For list pages with search and infinite scroll, extend `maintenance/global_list_base.html` instead.

For simple centered pages (like error pages), extend `layouts/minimal_centered.html` which provides a `centered_content` block. Error pages extend `layouts/error.html` which builds on this with a consistent icon/heading/message structure.

## Component Expectations

The project establishes component patterns in [flipfix/static/core/styles.css](../flipfix/static/core/styles.css). Before creating new components, review existing patterns:

### Layout Components

- **Page Header** (`.page-header` with `.page-header__left`, `.page-header__right` for breadcrumbs and actions)
- **List Header** (`.list-header` with `.list-header__left`, `.list-header__right` for search/filters and actions)
- **Section Header** (`.section-header` with `.section-header__actions` for h2 headings with inline actions)
- **Flip Card** (`.flip-card` with `.flip-card__top`, `.flip-card__main`, `.flip-card__bottom` and optional left/right sub-elements for aligning content; use `.flip-card--clickable` when the whole card should be a link, and `.flip-card-list` to reset list spacing when rendering multiple flip-cards)
- **Centered Container** (`.centered-container` - flexbox container that vertically and horizontally centers content)
- **Wall Card** (`.wall-card` with `.wall-card__header`, `.wall-card__row`, `.wall-card__desc`, `.wall-card__time`, `.wall-card__overflow` — grouped machine card for the wall display board; used inside `.column-grid.wall-display`)

### UI Components

- **Buttons** (`.btn` with modifiers like `.btn--primary`, `.btn--secondary`, `.btn--log`, `.btn--report`)
- **Badges, Tags, Pills** (`.badge` with status modifiers like `.badge-open`, `.badge-fixing`, `.badge-inline`)
- **Cards** (`.card` with BEM elements like `.card__header`, `.card__body`)
- **Forms** (`.form-field` wrapper pattern, `.form-inline` for inline forms) - See [Forms.md](Forms.md) for form building patterns and components
- **Messages & Alerts** (`.message` with type modifiers like `.message--success`, `.message--error`)
- **User Menu** (`.user-menu` with `.user-menu__avatar`, `.user-menu__dropdown`, `.user-menu__item`)
- **Priority+ Nav** (`.nav--priority` with `.nav-priority__item`, `.nav-priority__label`, `.nav-priority__dropdown`, `.nav-priority__dropdown-group`, `.nav-priority__dropdown-heading`) — mobile nav bar that shows 2–4 items with icons and labels depending on viewport width, plus a Menu button that opens a dropdown with all nav items, admin section, and account actions. Items progressively enter the bar at 420px (Logs) and 540px (Parts). Template: `core/partials/nav_header.html`.

### Interactive Components

- **Inline Edit** (`.inline-edit-group`, `.inline-edit-field`, `.inline-edit-select`)
- **Task List Checkboxes** (`.task-list-item` with checkbox input - rendered from markdown task list syntax: `- [ ]`, `* [ ]`, `+ [ ]`, `1. [ ]`, and inside blockquotes)
- **Status Indicator** (`.status-indicator` with modifiers `.saving`, `.saved`, `.error`) — card-level, used by `text_edit.js`
- **Save Status** (`.save-status` with modifiers `.save-status--saving`, `.save-status--saved`, `.save-status--error`, `.save-status--fade`) — page-level breadcrumb indicator, used by `save_status.js`
- **Media Grid** (`.media-grid`, `.media-item`, `.media-link`, `.media-video`, `.btn-delete-media`)

### Utility Classes

- `.hidden` - Hide elements (use with JS classList.add/remove for toggling)
- `.visually-hidden` - Hide visually but keep accessible to screen readers (see [Icons](#icons))
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

Use `block--modifier` when adding variants (colors, sizes, states). Examples:

- `.btn--primary`, `.btn--secondary`, `.btn--log`
- `.pill--neutral`, `.pill--status-good`, `.pill--status-broken`

### Don't use hyphens for standalone utilities

Use simple names for standalone utilities (`.card`, `.btn`, `.hidden`)

## Responsive Design

The site must be optimized for mobile, tablet, and desktop. Avoid tables; hard to make those responsive.

The stylesheet is **mobile-first**: unprefixed rules are the phone state, and `min-width` queries progressively re-enable wider layouts. There are no `max-width` queries, and adding one would break the parity checker (see below) on purpose.

Breakpoints, all `min-width`:

| Width  | What changes                                                        |
| ------ | ------------------------------------------------------------------- |
| 420px  | `Logs` enters the priority nav bar                                  |
| 540px  | `Parts` enters the priority nav bar                                 |
| 640px  | Filter bar goes horizontal; machine-card buttons gain short labels  |
| 768px  | Desktop nav replaces the mobile nav; breadcrumb actions gain labels |
| 900px  | Machine-card buttons gain full labels                               |
| 1024px | Sidebar moves from stacked above the main column to beside it       |

### Mobile/desktop parity

`layouts/two_column.html` renders `{% block sidebar %}` and `{% block main %}` as siblings of a flex column. **The sidebar is never hidden** — below 1024px it stacks above the main column, and from 1024px it sits alongside it. So anything you put in `sidebar` is reachable at every width, and no mobile counterpart is needed.

It used to be `display: none` below 1024px with a parallel `{% block mobile_actions %}` for phones. Keeping the two in step was manual, they drifted, and 92 affordances ended up unreachable on a phone — including the whole docs navigation and the "mark task done" buttons. `mobile_actions` no longer exists; do not reintroduce a second copy of anything.

**Sidebar above or below the main column.** The default is above, which is right for lists, feeds, detail pages and forms. Pages whose sidebar is long-form navigation and whose main column is the thing the reader came for can opt out:

```django
{% block two_column_modifier %}two-column--sidebar-last{% endblock %}
```

Only the wiki does this today (`wiki/base.html`, with `wiki/home.html` and `wiki/reorder.html` opting back out).

**Do not use that modifier on a page whose main column grows by infinite scroll.** The scroll sentinel sits at the end of the main column, so scrolling toward the sidebar loads more rows and pushes it further away — it becomes permanently unreachable. The parity checker cannot detect this; it resolves `display`, not reachability. Affected pages today: the activity feed, logs and parts lists, the machine feed, and the problem-report and part-request detail timelines.

This is enforced. `manage.py check_mobile_parity` reports affordances reachable at 1280px but not at 390px, and a test holds the result against a baseline that may only shrink. See [`MobileParity.md`](MobileParity.md).

## Accessibility & Interaction

- Use semantic HTML elements (e.g., `<nav>`, `<main>`, `<section>`, `<table>`).
- Maintain WCAG AA contrast for text/background combinations.
- Do not remove focus outlines without providing explicit `:focus-visible` styles with equal or better visibility.
- Buttons and links should have hover + active states distinct from focus.
- Respect `@media (prefers-reduced-motion: reduce)` by disabling transitions.

### Icons

This project uses [Font Awesome](https://fontawesome.com/icons) icons. Always use the `{% icon %}` template tag instead of raw `<i>` elements because the tag handles accessibility automatically.

| Usage                                 | Description                                                                                                                                               |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `{% icon "check" %}`                  | Uses icon `fa-check` from the default Font Awesome collection, Solid                                                                                      |
| `{% icon "discord" style="brands" %}` | Uses icon `fa-discord` from the Brands collection                                                                                                         |
| `{% icon "check" class="meta" %}`     | Adds `meta` CSS class                                                                                                                                     |
| `{% icon "check" label="Problem" %}`  | Create the label `Problem` for screen readers. Use only when icon conveys meaning not in adjacent text. By default, icons are hidden from screen readers. |

## XSS Protection

Django auto-escapes `{{ variable }}` output. User-submitted text is safe to display.

Only use `{{ variable|safe }}` for HTML you control (e.g., markdown rendered server-side).

## Performance & Build

- Single vanilla CSS file (`styles.css`) for cacheability
- Static files are gzipped and fingerprinted via WhiteNoise + `collectstatic`
- Inter font loaded from Google Fonts with `display=swap`
