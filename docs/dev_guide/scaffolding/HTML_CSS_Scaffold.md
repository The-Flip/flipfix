# HTML & CSS Scaffold Reference

Use this document when regenerating the base UI from scratch. It captures the design tokens, layout defaults, and breakpoint rules that the initial build used. Day-to-day maintenance work should refer to [`../HTML_CSS_Guide.md`](../HTML_CSS_Guide.md), while this file is for scaffolding or large visual refreshes.

## Visual System & Tokens

- **Typography:** Use the system stack `"Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif` but do not load remote fonts; the stack simply falls back if fonts are missing.
- **Color Palette:**
  - Primary: `#1f7aea` – links, primary buttons
  - Secondary: `#0f1f34` – headers, navigation backgrounds
  - Accent: `#10b981` – success highlights
  - Warning: `#f59e0b`, Danger: `#ef4444`
  - Surface light: `#ffffff`, Surface muted: `#f5f7fb`, Border: `#e3e8ef`
  - Text base: `#1f2933`, Text muted: `#52606d`
- **Spacing Scale:** 4px base unit with tokens `space-1 = 4px`, `space-2 = 8px`, up to `space-6 = 24px`.
- **Radii & Shadows:** Base radius `4px`, cards `8px`. Shared shadow `0 8px 20px rgba(15, 23, 42, 0.08)`.
- **Token Declaration:** Define CSS custom properties within `:root` (`--color-primary`, `--space-3`, etc.) and reference those variables everywhere instead of raw values.

## Layout & Responsive Baseline

- **Mobile First:** Default styles target small screens; layer larger breakpoint refinements via `@media` queries.
- **Container:** Max width `1200px`, horizontal padding `space-4`, background `#f5f7fb`.
- **Header/Nav/Footer:** Sticky navigation on desktop (`position: sticky; top: 0`) with a simple centered footer.
- **Responsive Breakpoints:**
  - `@media (max-width: 1024px)`: collapse sidebar navigation into horizontal tabs.
  - `@media (max-width: 768px)`: stack header elements, convert multi-column grids to a single column.
  - `@media (max-width: 480px)`: make buttons full-width and expand body padding.
- **Data Display:** Prefer card/list layouts for primary content. Use tables only for strongly tabular admin screens and provide a stacked fallback when width < 768px.
- **Spacing Rhythm:** Maintain `space-4` (16px) between stacked sections and `space-2` (8px) between tightly related elements.

## Component Baselines

These defaults were used when generating the original component library. Match them if you rebuild the CSS bundle from scratch.

- **Buttons:** `.btn` with modifiers for primary/secondary/danger/ghost. Each variant defines `:hover`, `:focus-visible`, and `:disabled` states using the palette above.
- **Cards:** `.card` surfaces with padding `space-5`, background `#fff`, shared shadow token, and radius `8px`.
- **Forms:** `.form-field` wrapper containing `<label>` + control. Inputs use `border: 1px solid var(--border-color)`, `border-radius: 6px`, and a focus ring `box-shadow: 0 0 0 3px rgba(31, 122, 234, 0.25)` while retaining the browser outline.
- **Utilities:** Provide lightweight spacing (`.mt-4`, `.gap-2`), layout (`.flex`, `.grid-two`), and text utility classes to prevent inline styles.

## Build & File Layout

- Place CSS sources under `static/css/` with files such as `base.css` (reset + tokens), `layout.css`, and `components.css`. Concatenate or import them into a single bundle.
- Stick to vanilla CSS compiled once; no frameworks or remote font loads baked into the scaffold.
- During `collectstatic`, fingerprint the compiled CSS to leverage caching on Render/production.
