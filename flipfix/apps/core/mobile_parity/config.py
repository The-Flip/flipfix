"""Tuning knobs for the mobile/desktop parity audit.

Everything an operator is likely to want to adjust lives here rather than being
scattered through the audit modules. See ``docs/MobileParity.md``.
"""

from __future__ import annotations

from typing import Final

# --- Viewport widths -------------------------------------------------------

#: The narrow viewport we audit. 390px is the iPhone 14/15 logical width and
#: sits below every breakpoint the stylesheet defines.
MOBILE_WIDTH: Final = 390

#: The wide viewport we audit. 1280px clears the largest breakpoint (1024px).
DESKTOP_WIDTH: Final = 1280

# --- Affordance extraction -------------------------------------------------

#: Tags that represent something a person can *do*. A desktop-only action is an
#: error: the user simply cannot perform it on a phone.
#:
#: ``form`` is deliberately absent. A form is only reachable through its fields
#: and submit controls, which are extracted in their own right, so counting the
#: element as well would report every form twice.
ACTION_TAGS: Final = frozenset({"a", "button", "input", "select", "textarea"})

#: Input types that are not really user-facing affordances.
IGNORED_INPUT_TYPES: Final = frozenset({"hidden", "csrfmiddlewaretoken"})

#: Tags that carry page *information*. A desktop-only heading is a warning: the
#: page still works on a phone, but something is missing from it.
#:
#: Deliberately narrow. Scanning every paragraph turns the report into wallpaper
#: nobody reads, which is the main way a tool like this dies. If the first run
#: floods, narrow this further rather than weakening the gate.
CONTENT_TAGS: Final = frozenset({"h1", "h2", "h3", "h4", "caption", "th", "dt"})

#: Classes treated as content anchors regardless of their tag.
CONTENT_CLASSES: Final = frozenset({"sidebar__title", "stat__label", "section-header__title"})

# --- Things that are hidden, but not by the viewport -----------------------

#: Classes that hide an element as *interaction state* rather than as a
#: viewport rule. ``.hidden`` is the project's JS open/closed toggle: it is what
#: ``toggleDropdown()`` adds and removes (``core.js``), so markup inside a
#: collapsed dropdown is one tap away rather than missing. Treating it as
#: hiding would report the whole hamburger menu as a mobile gap.
#:
#: These classes are stripped from an element before its display is resolved.
NON_VIEWPORT_HIDDEN_CLASSES: Final = frozenset({"hidden"})

#: Attributes marking a control that only discloses other markup. The menu it
#: opens is enumerated on its own, so counting the toggle as well would report a
#: gap whenever the same items are reached through a different control on the
#: other viewport (desktop avatar menu versus mobile hamburger).
DISCLOSURE_ATTRS: Final = frozenset({"aria-haspopup", "aria-controls"})

# --- Known equivalences ----------------------------------------------------

#: Maps an affordance key to the key it should be considered identical to.
#:
#: Use this only when the same capability is genuinely offered through different
#: markup on each side (a desktop ``<a>`` versus a mobile ``<button>``, say).
#: Every entry is a design smell being papered over, so keep this small and
#: explain each one.
KEY_ALIASES: Final[dict[str, str]] = {}

# --- Reporting -------------------------------------------------------------

#: Truncation length for the slug portion of a generated key.
MAX_KEY_SLUG_LENGTH: Final = 48
