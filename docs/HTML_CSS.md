# HTML & CSS Development Guide

This is a guide for developers and AI assistants creating HTML and CSS.

Focus on clean, modern, lightweight mobile-first pages that rely only on system fonts and a single cached stylesheet.

## 1. Design System Reference

When generating the initial stylesheets, use the color tokens, spacing scales, baseline layout rules, and other scaffold details from [`scaffolding/HTML_CSS_Scaffold.md`](scaffolding/HTML_CSS_Scaffold.md). Review that file when regenerating the base stylesheet or updating global design tokens.

The rest of this guide focuses on day-to-day markup and component expectations.

## 2. Things to Avoid

- **Do not introduce new font stacks** or load remote fonts. Rely on the font stack defined in the base stylesheet.
- **Do not hardcode colors, spacing, or shadows.** Reference the CSS variables and tokens established in the base stylesheet.
- **Do not use inline styles (`style=`)** — rely on reusable classes or scoped CSS files instead.
- **Do not drop new component patterns** without documenting them; align with the component expectations below.
- **Do not remove focus outlines** without providing explicit `:focus-visible` styles with equal or better visibility.

## 3. Component Expectations

- **Buttons:** `.btn`, modifiers for primary/secondary/danger/ghost. Provide `:hover`, `:focus-visible`, and `:disabled` states with accessible contrast.
- **Badges/Tags:** Consistent height, uppercase text, left padding `space-2`.
- **Cards/Blocks:** `.card` for reusable white surfaces with padding `space-5`, `box-shadow` token.
- **Forms:** `.form-field` wrapper holding `<label>` and control. Inputs get `border: 1px solid var(--border-color)`, `border-radius: 6px`, focus ring `box-shadow: 0 0 0 3px rgba(31, 122, 234, 0.25)` while retaining visible outline.
- **Messages & Alerts:** `.alert`, `.alert--success`, `.alert--danger`, etc., leveraging palette tokens.
- **List Cards:** Use flex layouts with `gap` for metadata rows. Provide `.clickable-card` helper with `cursor: pointer` and subtle background change on hover. Include a `.list-card__meta` element for secondary text so output matches layouts that show author/time/status details.
- **Utilities:** Provide light utilities for spacing (`.mt-4`), layout (`.flex`, `.grid-two`), and text alignment to avoid inline style usage.

## 4. Accessibility & Interaction

- Maintain WCAG AA contrast for text/background combinations.
- Never remove outlines without providing `:focus-visible` alternatives.
- Respect `@media (prefers-reduced-motion: reduce)` by disabling transitions.
- Buttons and links should have hover + active states distinct from focus.
- Use semantic HTML elements (e.g., `<nav>`, `<main>`, `<section>`, `<table>`).

## 5. Organizational Rules

- **File Structure:** Place CSS sources under the project’s `static/css/` directory (or equivalent) with files such as `base.css` (reset + tokens), `layout.css`, `components.css`, and page-specific modules (`dashboard.css`, `reports.css`, etc.). Concatenate/minify them into a single bundle that the main layout template includes.
- **No Inline Styles:** Templates should only use class names. Add page-specific CSS via additional `<link>` tags or template blocks instead of `style=` attributes.
- **Naming Methodologies:**
  1. **BEM:** `block__element--modifier` (e.g., `record-card__meta--muted`). Clear intent, low collision risk.
  2. **Namespaced Modules:** Prefix class names per page/component (e.g., `.machine-detail-header`, `.machine-detail-meta`). Works well when pages are isolated.
  3. **Utility-First Hybrid:** Small reusable classes (`.text-muted`, `.gap-4`, `.flex-between`) combined with semantic wrappers. Enables rapid layout changes with fewer bespoke selectors. Pick one primary strategy and document modifiers/helpers.

## 6. Performance & Build

- Stick to vanilla CSS compiled once (no external fonts, minimal animations).
- Use `@layer base, components, utilities;` to control cascade if desired.
- Minify production CSS and ensure it is fingerprinted via Django’s `collectstatic`.
- Document a command such as `npm run css:build` if tooling is added later, but current instructions assume plain CSS maintained manually.

## 7. Deliverables Checklist

 - Reference the tokens defined in the scaffold doc.
 - Write base reset + typography rules.
 - Implement components with agreed naming method.
 - Provide responsive behavior for header, main grids, tables, and cards at the specified breakpoints.
 - Ensure no inline styles remain; all templates rely solely on classes.
 - Verify focus styles and reduced-motion handling.
 - Keep CSS lean: no unused classes or framework imports.
