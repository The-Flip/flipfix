"""Parse ``display`` declarations out of the project stylesheet.

The parity audit needs one narrow fact about the CSS: for a given set of class
names and a given viewport width, is the element ``display: none``?

That is answerable exactly — not approximately — because this project's
stylesheet is unusually disciplined:

* it is a single hand-written file with no build step,
* it is mobile-first and contains **no** ``max-width`` media queries, so a rule
  inside ``@media (min-width: N)`` simply applies from ``N`` upwards, and
* every width-conditional ``display`` rule uses a bare single-class selector,
  so all such rules share the same specificity and plain source order decides.

Those three properties are what let us skip a browser. They are also
assumptions, so this module **raises rather than guesses** whenever it meets CSS
it does not model: see :class:`UnsupportedCssError`. A silent wrong answer here
would quietly corrupt the audit; a loud failure just breaks the build with a
line number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

STYLESHEET_RELATIVE_PATH = "flipfix/static/core/styles.css"

_MIN_WIDTH_MEDIA_RE = re.compile(r"^@media\s*\(\s*min-width\s*:\s*(\d+)px\s*\)$")
_BARE_CLASS_RE = re.compile(r"^\.([A-Za-z_][\w-]*)$")
_CLASS_IN_SELECTOR_RE = re.compile(r"\.([A-Za-z_][\w-]*)")
_COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")


class UnsupportedCssError(Exception):
    """The stylesheet uses a construct the parity resolver cannot model.

    Raised instead of falling back to a guess. The message always names the
    offending line so the fix is obvious.
    """


@dataclass(frozen=True)
class DisplayRule:
    """A single ``display`` declaration on a bare single-class selector."""

    class_name: str
    value: str
    min_width: int
    important: bool
    order: int
    line: int

    @property
    def is_hidden(self) -> bool:
        return self.value == "none"


@dataclass(frozen=True)
class _PendingSelector:
    """A non-bare selector carrying a ``display``, validated after the parse."""

    selector: str
    value: str
    line: int


@dataclass(frozen=True)
class DisplayIndex:
    """Resolved ``display`` behaviour for every class the stylesheet styles."""

    rules: tuple[DisplayRule, ...]
    breakpoints: tuple[int, ...]
    source: str

    def winning_rule(self, class_names: frozenset[str], width: int) -> DisplayRule | None:
        """Return the ``display`` rule that wins for these classes at this width.

        All candidate selectors are bare single classes, so they tie on
        specificity and the cascade reduces to ``!important`` first, then source
        order.
        """
        winner: DisplayRule | None = None
        for rule in self.rules:
            if rule.min_width > width or rule.class_name not in class_names:
                continue
            if winner is None or (rule.important, rule.order) >= (winner.important, winner.order):
                winner = rule
        return winner

    def display_for(self, class_names: frozenset[str], width: int) -> str | None:
        """Return the winning ``display`` value, or ``None`` if unstyled."""
        winner = self.winning_rule(class_names, width)
        return winner.value if winner else None

    def is_hidden(self, class_names: frozenset[str], width: int) -> bool:
        return self.display_for(class_names, width) == "none"

    def sample_widths(self) -> tuple[int, ...]:
        """One representative width per band the breakpoints carve out."""
        return (0, *self.breakpoints)

    def toggle_classes(self) -> frozenset[str]:
        """Classes whose ``display`` changes with viewport width."""
        toggles = set()
        for class_name in {rule.class_name for rule in self.rules}:
            single = frozenset({class_name})
            values = {self.display_for(single, width) for width in self.sample_widths()}
            if len(values) > 1:
                toggles.add(class_name)
        return frozenset(toggles)

    def revealed_at(self, class_name: str) -> int | None:
        """Narrowest width at which ``class_name`` stops hiding its element.

        Returns ``None`` when the class hides at every width (``.hidden``) or
        never hides at all.
        """
        single = frozenset({class_name})
        if not self.is_hidden(single, 0):
            return None
        for width in self.sample_widths():
            if not self.is_hidden(single, width):
                return width
        return None


def _strip_comments(css: str) -> str:
    """Blank out ``/* ... */`` while preserving line numbering."""
    out: list[str] = []
    index = 0
    length = len(css)
    while index < length:
        if css.startswith("/*", index):
            end = css.find("*/", index + 2)
            end = length if end == -1 else end + 2
            out.append("".join(ch if ch == "\n" else " " for ch in css[index:end]))
            index = end
        else:
            out.append(css[index])
            index += 1
    return "".join(out)


def _parse_media_min_width(prelude: str, line: int) -> int | None:
    """Return the ``min-width`` of a media prelude, or ``None`` if it is opaque.

    "Opaque" means we do not model it — ``prefers-color-scheme`` and friends.
    Opaque blocks are tolerated as long as they declare no ``display``.
    """
    normalised = " ".join(prelude.split())
    match = _MIN_WIDTH_MEDIA_RE.match(normalised)
    if match:
        return int(match.group(1))
    if normalised.startswith("@media") and "max-width" in normalised:
        raise UnsupportedCssError(
            f"line {line}: {normalised!r} — this resolver assumes a mobile-first "
            "stylesheet with only min-width queries. A max-width query inverts that "
            "model, so the parity audit would report the opposite of the truth."
        )
    return None


def _subject_classes(selector: str) -> frozenset[str]:
    """Classes in the selector's subject (its final compound)."""
    subject = _COMBINATOR_RE.split(selector.strip())[-1]
    return frozenset(_CLASS_IN_SELECTOR_RE.findall(subject))


def parse_display_index(css: str, *, source: str = STYLESHEET_RELATIVE_PATH) -> DisplayIndex:
    """Build a :class:`DisplayIndex` from stylesheet text.

    Raises:
        UnsupportedCssError: on any construct the resolver does not model.
    """
    text = _strip_comments(css)
    rules: list[DisplayRule] = []
    pending: list[_PendingSelector] = []
    breakpoints: set[int] = set()

    stack: list[tuple[str, str, int]] = []  # (kind, prelude, line)
    buffer: list[str] = []
    line = 1
    order = 0

    def current_min_width() -> int:
        widths = [
            _parse_media_min_width(prelude, at_line) or 0
            for kind, prelude, at_line in stack
            if kind == "at"
        ]
        return max(widths, default=0)

    def in_opaque_at_rule() -> bool:
        return any(
            _parse_media_min_width(prelude, at_line) is None
            for kind, prelude, at_line in stack
            if kind == "at"
        )

    def record(declaration: str, at_line: int) -> None:
        nonlocal order
        if ":" not in declaration:
            return
        prop, _, raw_value = declaration.partition(":")
        if prop.strip().lower() != "display":
            return
        if not stack or stack[-1][0] != "rule":
            raise UnsupportedCssError(
                f"line {at_line}: a 'display' declaration outside any style rule."
            )
        if in_opaque_at_rule():
            opaque = next(
                prelude
                for kind, prelude, rule_line in stack
                if kind == "at" and _parse_media_min_width(prelude, rule_line) is None
            )
            raise UnsupportedCssError(
                f"line {at_line}: 'display' declared inside {opaque!r}. The parity "
                "resolver only models width-based visibility."
            )

        value = " ".join(raw_value.split())
        important = value.endswith("!important")
        if important:
            value = value[: -len("!important")].strip()

        selector = stack[-1][1]
        min_width = current_min_width()
        for part in (piece.strip() for piece in selector.split(",")):
            if not part:
                continue
            match = _BARE_CLASS_RE.match(part)
            if match:
                rules.append(
                    DisplayRule(
                        class_name=match.group(1),
                        value=value,
                        min_width=min_width,
                        important=important,
                        order=order,
                        line=at_line,
                    )
                )
                order += 1
            else:
                pending.append(_PendingSelector(selector=part, value=value, line=at_line))

    for char in text:
        if char == "{":
            prelude = "".join(buffer).strip()
            buffer.clear()
            if prelude.startswith("@"):
                min_width = _parse_media_min_width(prelude, line)
                if min_width:
                    breakpoints.add(min_width)
                stack.append(("at", prelude, line))
            else:
                if stack and stack[-1][0] == "rule":
                    raise UnsupportedCssError(
                        f"line {line}: nested style rule {prelude!r}. CSS nesting changes "
                        "how selectors resolve and is not modelled."
                    )
                stack.append(("rule", prelude, line))
        elif char == "}":
            leftover = "".join(buffer).strip()
            buffer.clear()
            if leftover:
                record(leftover, line)
            if not stack:
                raise UnsupportedCssError(f"line {line}: unbalanced '}}' in {source}.")
            stack.pop()
        elif char == ";":
            declaration = "".join(buffer).strip()
            buffer.clear()
            if declaration:
                record(declaration, line)
        else:
            buffer.append(char)
        if char == "\n":
            line += 1

    if stack:
        kind, prelude, at_line = stack[-1]
        raise UnsupportedCssError(f"line {at_line}: unclosed {kind} block {prelude!r} in {source}.")

    index = DisplayIndex(
        rules=tuple(rules),
        breakpoints=tuple(sorted(breakpoints)),
        source=source,
    )

    # A non-bare selector is harmless as long as it does not set 'display' on a
    # class whose visibility we track: those would out-specify our flat model.
    toggles = index.toggle_classes()
    for entry in pending:
        clash = _subject_classes(entry.selector) & toggles
        if clash:
            raise UnsupportedCssError(
                f"line {entry.line}: selector {entry.selector!r} sets 'display' on "
                f"viewport-toggled {sorted(clash)}. The parity resolver assumes flat "
                "specificity for toggle classes, so this rule would be mis-ranked."
            )

    return index


@lru_cache(maxsize=1)
def load_display_index() -> DisplayIndex:
    """Parse the project stylesheet once per process."""
    path = Path(settings.BASE_DIR) / STYLESHEET_RELATIVE_PATH
    return parse_display_index(path.read_text(encoding="utf-8"), source=STYLESHEET_RELATIVE_PATH)
