# Mobile/Desktop UI Parity

`layouts/two_column.html` renders `{% block sidebar %}` and `{% block main %}` as
siblings of a flex column. The sidebar is **never hidden**: below 1024px it stacks
above the main column, and from 1024px it sits alongside it.

That was not always true. It used to be `display: none` below 1024px, with a
parallel `{% block mobile_actions %}` that each page had to keep in step by hand.
They drifted, and this tool was built to find out how far: **92 affordances** were
reachable on a desktop and not on a phone, including the entire docs navigation and
the buttons for marking maintenance tasks done. The fix was structural — stop hiding
the sidebar, delete `mobile_actions` — so the baseline is now empty and this tool's
job is to keep it that way.

`manage.py check_mobile_parity` finds any new drift, and
`flipfix/apps/core/tests/test_mobile_parity_audit.py` fails the build on it.

## Running it

```bash
# The report
python manage.py check_mobile_parity
python manage.py check_mobile_parity --route wiki-page-detail
python manage.py check_mobile_parity --json | jq '.baseline'

# After fixing a gap: drop entries that no longer reproduce
python manage.py check_mobile_parity --update-baseline

# After deliberately adding one: also record what is new
python manage.py check_mobile_parity --update-baseline --accept-new
```

The command builds a throwaway test database, renders against it, and rolls the
fixtures back. It never touches your development data.

## How it works

No browser is involved. That is affordable here because **every responsive
behaviour in this project is CSS** — there is no viewport logic in any
JavaScript — and the stylesheet is unusually tractable: one hand-written file,
mobile-first, no `max-width` queries, and a dozen `display: none` rules on bare
single-class selectors.

The pipeline, in `flipfix/apps/core/mobile_parity/`:

| Module           | Job                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------- |
| `css_rules.py`   | Parse `styles.css` into a `DisplayIndex`: which classes set `display`, at which `min-width`. |
| `dom.py`         | Build a strict element tree from the rendered HTML.                                          |
| `affordances.py` | Extract each action and content anchor, and give it a stable key.                            |
| `visibility.py`  | Walk the ancestor chain to decide whether an element displays at a width.                    |
| `routes.py`      | Enumerate the pages, the fixtures they need, and the personas to view them as.               |
| `audit.py`       | Render each page once, resolve it at 390px and 1280px, diff the two.                         |
| `baseline.py`    | Read, diff and write `baseline.json`.                                                        |

A gap is a plain set difference: keys visible at 1280px minus keys visible at
390px. Counting is never involved, so the same affordance rendered twice cancels
itself out. That mattered when pages carried two copies of their actions; they no
longer do, and duplicating markup is **not** the way to fix a gap now — make the
affordance reachable at both widths instead.

### Keys

Keys identify what an affordance _targets_, never what it is _called_:

```
link:<url_name>                        <a href>, resolved through django.urls
link:external:<host><path>             off-site link
link:fragment:<slug>                   in-page anchor
form:<url_name>:<method>               a form, via its submit control
form:<url_name>:<method>#<name>=<val>  a named submit button
field:<form-key>:<name>                an input, select or textarea
button:<slug>                          a button with no form (JS-driven)
content:<slug>                         a heading or labelled block
```

Two rules keep the baseline stable:

- **URL kwargs are dropped.** `/machines/parity-machine/edit/` keys as
  `link:machine-edit`, so fixture slugs never leak into the baseline.
- **Names are never part of an action's key.** `.machine-card__btn-text--short`
  and `--long` swap a link's text at 640px and 900px; keying on the name would
  make every machine card look like a gap.

Content text is normalised before slugifying — digit runs become `N`, dates
become `DATE` — so counters and timestamps do not churn the baseline.

### What is deliberately _not_ an affordance

- **Elements inside `.hidden`.** That class is the JS open/closed state applied
  by `toggleDropdown()`, not a viewport rule. A collapsed hamburger menu is one
  tap away, not missing, so `.hidden` is stripped before visibility is resolved.
  Without this the whole mobile nav would be reported as a gap.
- **Disclosure controls** — anything carrying `aria-haspopup` or `aria-controls`.
  The menu it opens is enumerated on its own, so counting the toggle as well
  would flag a gap whenever desktop and mobile use different chrome to reach the
  same items.
- **`<form>` elements themselves**, which are reachable only through their
  fields and submit buttons.
- **Hidden inputs.**

### Personas

| Persona      | Why it exists                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `maintainer` | The state most of the UI targets, and the only one where `can_access_maintainer_portal` is true — so the only one that exercises `.avatar-dropdown--mobile-hidden`. |
| `anonymous`  | Rendered with `PUBLIC_ACCESS_ENABLED` on. A materially different DOM.                                                                                               |
| `superuser`  | The only way to reach `access="superuser"` pages, and what pins down admin-menu parity.                                                                             |

A plain authenticated non-maintainer is **deliberately absent**: its only unique
surface is the profile and password-change pages, both already covered by
`maintainer`, and it is denied everywhere else.

### Which pages get audited

Routes come from `get_registered_routes()` in `flipfix/apps/core/routing.py`,
which records the `access=` level of everything declared through the project's
own `path()`. Django's admin is not declared that way, so it drops out without a
single exclusion entry.

Most filtering then happens **after** rendering: anything that is not a 200, not
`text/html`, or has no `<body>` is skipped with a recorded reason. That catches
every POST-only endpoint, redirect and JSON view on its own, and keeps doing so
as the site changes. `EXCLUDED_ROUTES` only lists pages that _do_ return HTML but
should not be audited, such as the fixed-size wall display.

A parameterised route with neither a `ROUTE_KWARGS` entry nor an exclusion raises
`UnmappedRouteError`. A new page must be deliberately covered or deliberately
skipped, never quietly dropped.

## The baseline

`flipfix/apps/core/mobile_parity/baseline.json` is **currently empty** — there are
no known gaps, so any finding is a regression. It keeps two sections for when one
is needed:

- **`gaps`** — real defects not yet fixed. This is the ratchet. The test fails
  when it grows, and equally when an entry stops reproducing but is left behind.
  That second direction is what forces the list to shrink.
- **`accepted`** — differences that are deliberate, each with a written `reason`.
  Loading fails if a reason is missing. `--update-baseline` never writes here:
  promoting an entry is a hand edit, which puts it in front of a reviewer.

Only `route`, `persona` and `key` are matched on. `label`, `element`,
`hidden_by` and `revealed_at` are description, refreshed on every update, so
markup churn shows in the diff without failing the build.

Staleness is only judged for pages a run actually rendered. A page filtered out
with `--route`, or one that has started erroring, tells us nothing about whether
its gaps were fixed.

## When the parser refuses

`css_rules.py` raises `UnsupportedCssError` rather than guessing. The two that
matter:

- **A `max-width` media query.** The resolver assumes mobile-first `min-width`
  only. One `max-width` rule inverts that model, and the audit would report the
  opposite of the truth. This is the single assumption the whole no-browser
  approach rests on, so it fails the build instead.
- **A compound selector setting `display` on a viewport-toggled class**, e.g.
  `.wrapper .two-column__sidebar { display: block }`. All toggle rules currently
  share one specificity, which is why plain source order resolves them. A rule
  like that would out-specify the model and be mis-ranked.

`dom.py` raises `MalformedHtmlError` when tags do not nest, because the audit
reads ancestor chains to decide visibility. Templates are djlint-formatted, so
this firing means a genuine markup bug.

## Blind spots

**This tool does not see:**

1. **Reachability.** It resolves `display`, so it reports an element as present the
   moment it is in flow — even if nobody can practically scroll to it. The sharp
   case is infinite scroll: the sentinel sits at the end of the main column, so a
   sidebar placed _after_ main recedes as more rows load and is never reached. Both
   orderings of the stack therefore look identical to the checker, and the choice
   has to be made by eye. This is why `two-column--sidebar-last` must never be used
   on a page with infinite scroll — see `HTML_CSS.md`.
2. **Overflow and clipping.** `.filter-bar__filters { overflow-x: auto }` scrolls
   its pills off the side of a phone. The DOM says visible. This is the biggest
   false negative and there is no fix without real layout.
3. **JavaScript that changes the DOM.** `catalog_chart.js` demotes the
   `<table>` fallback in `catalog/explore.html` to `.visually-hidden` once the
   SVG paints, so the audit sees a table no user does. The audit is of the
   pre-JS server-rendered page.
4. **Anything that is not `display`** — `visibility`, `opacity`, zero heights,
   transforms, `pointer-events`, z-index occlusion.
5. **Unpopulated template branches.** Only what `build_fixtures()` creates gets
   rendered. Affordances behind `{% if machine.owner %}` are invisible unless the
   fixture sets it. **The fixtures are a coverage surface** — extend them when
   you add conditional markup.
6. **Empty-state markup**, which the populated fixtures never trigger.
7. **Permission combinations beyond the three personas** — `can_manage_catalog`,
   catalog-manager-only, terminal-manager.
8. **Click handlers on `<div>`s** and drag-reorder targets, which are not in
   `ACTION_TAGS`.

**It can also over-report:** a desktop `<a>` and a mobile `<button>` that do the
same job get different keys. `KEY_ALIASES` in `config.py` exists for that, but
every entry is a maintenance liability, so prefer fixing the markup.

## A note on the name

"Mobile" understates what this checks. The layout breakpoint is 1024px, so a 900px
tablet and a half-width laptop window are on the narrow side of it too. Every
finding prints its real `revealed_at` width for that reason.
