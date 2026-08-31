"""Turn a parsed page into keyed affordances.

An *affordance* is one thing the page offers: an action a person can take, or a
piece of information it shows. Each gets a stable key so the same affordance
rendered twice — once in ``.mobile-actions``, once in ``.two-column__sidebar`` —
collapses to a single entry, and so a baseline entry survives markup churn.

The keys are deliberately **target-derived, never name-derived**. The stylesheet
swaps a machine card's button text between 640px and 900px
(``.machine-card__btn-text--short`` / ``--long``), so folding an accessible name
into a link's key would make every machine card look like a parity gap. Names
are still captured, but only as a human-readable label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from django.urls import Resolver404, resolve
from django.utils.text import slugify

from flipfix.apps.core.mobile_parity.config import (
    ACTION_TAGS,
    CONTENT_CLASSES,
    CONTENT_TAGS,
    DISCLOSURE_ATTRS,
    IGNORED_INPUT_TYPES,
    KEY_ALIASES,
    MAX_KEY_SLUG_LENGTH,
)
from flipfix.apps.core.mobile_parity.dom import Element

Kind = Literal["action", "content"]

_DIGITS_RE = re.compile(r"\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")


@dataclass(frozen=True)
class Affordance:
    """One keyed thing the page offers."""

    key: str
    kind: Kind
    tag: str
    label: str

    @property
    def is_action(self) -> bool:
        return self.kind == "action"


def accessible_name(element: Element) -> str:
    """Best available human-readable name for ``element``.

    Follows the shape of the accessible name computation, far enough for our
    purposes. Notably the text branch includes ``.visually-hidden`` spans and
    excludes ``aria-hidden`` subtrees, which is exactly how ``{% icon %}`` names
    an icon-only control: it emits ``<i aria-hidden="true">`` beside a
    ``<span class="visually-hidden">Reorder Nav</span>``.
    """
    aria_label = element.attrs.get("aria-label", "").strip()
    if aria_label:
        return aria_label

    labelled_by = element.attrs.get("aria-labelledby", "").strip()
    if labelled_by:
        root = element.ancestors()[-1]
        names = [
            target.text()
            for target in (root.find_by_id(ref) for ref in labelled_by.split())
            if target is not None
        ]
        joined = " ".join(name for name in names if name).strip()
        if joined:
            return joined

    text = element.text().strip()
    if text:
        return text

    for attribute in ("title", "value", "placeholder", "alt"):
        value = element.attrs.get(attribute, "").strip()
        if value:
            return value

    for descendant in element.descendants():
        alt = descendant.attrs.get("alt", "").strip()
        if alt:
            return alt

    return ""


def _slug(text: str) -> str:
    return slugify(text)[:MAX_KEY_SLUG_LENGTH] or "unnamed"


def _normalise_content(text: str) -> str:
    """Blur out values that change with fixtures, keeping the wording."""
    text = _DATE_RE.sub("DATE", text)
    text = _TIME_RE.sub("TIME", text)
    return _DIGITS_RE.sub("N", text)


def _target(url: str) -> str:
    """Reduce a URL to a fixture-independent identifier.

    Resolving to a Django URL *name* and dropping the kwargs is what keeps
    baselines stable: ``/machines/parity-machine/edit/`` and
    ``/machines/anything-else/edit/`` both become ``machine-edit``.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme in {"mailto", "tel"}:
        return f"external:{parsed.scheme}"
    if parsed.netloc:
        return f"external:{parsed.netloc}{parsed.path}"
    if not parsed.path:
        return ""
    try:
        match = resolve(parsed.path)
    except Resolver404:
        return parsed.path
    return match.url_name or parsed.path


def _owning_form(element: Element) -> Element | None:
    for node in element.ancestors():
        if node.tag == "form":
            return node
    return None


def _form_key(form: Element) -> str:
    target = _target(form.attrs.get("action", "")) or "self"
    method = (form.attrs.get("method") or "get").lower()
    return f"form:{target}:{method}"


def _action_key(element: Element, label: str) -> str | None:
    tag = element.tag

    if tag == "a":
        href = element.attrs.get("href", "").strip()
        if not href or href.startswith("#"):
            return f"link:fragment:{_slug(label)}"
        if href.lower().startswith("javascript:"):
            return f"button:{_slug(label)}"
        target = _target(href)
        return f"link:{target}" if target else f"link:fragment:{_slug(label)}"

    if tag in {"input", "select", "textarea"}:
        input_type = element.attrs.get("type", "text").lower()
        if tag == "input" and input_type in IGNORED_INPUT_TYPES:
            return None
        name = element.attrs.get("name", "").strip()
        form = _owning_form(element)
        if input_type in {"submit", "image"}:
            if form is None:
                return f"button:{_slug(label)}"
            suffix = f"#{name}={element.attrs.get('value', '')}" if name else ""
            return f"{_form_key(form)}{suffix}"
        if not name:
            return None
        if name in IGNORED_INPUT_TYPES:
            return None
        scope = _form_key(form) if form is not None else "form:none:none"
        return f"field:{scope}:{name}"

    if tag == "button":
        form = _owning_form(element)
        button_type = element.attrs.get("type", "submit").lower()
        if form is not None and button_type == "submit":
            name = element.attrs.get("name", "").strip()
            suffix = f"#{name}={element.attrs.get('value', '')}" if name else ""
            return f"{_form_key(form)}{suffix}"
        return f"button:{_slug(label)}"

    return None


def is_disclosure_control(element: Element) -> bool:
    """True for a control whose only job is to reveal other markup.

    The revealed items are extracted independently, so counting the toggle too
    would flag a gap merely because desktop and mobile use different chrome to
    reach the same menu.
    """
    return bool(DISCLOSURE_ATTRS & element.attrs.keys())


def _is_content_anchor(element: Element) -> bool:
    return element.tag in CONTENT_TAGS or bool(element.classes & CONTENT_CLASSES)


def extract(root: Element) -> list[tuple[Element, Affordance]]:
    """Collect every affordance in the document, paired with its element."""
    found: list[tuple[Element, Affordance]] = []

    for element in root.descendants():
        if element.is_aria_hidden:
            continue

        label = accessible_name(element)

        if element.tag in ACTION_TAGS:
            if is_disclosure_control(element):
                continue
            key = _action_key(element, label)
            if key is not None:
                found.append(
                    (
                        element,
                        Affordance(
                            key=KEY_ALIASES.get(key, key),
                            kind="action",
                            tag=element.tag,
                            label=label,
                        ),
                    )
                )
            continue

        if _is_content_anchor(element) and label:
            key = f"content:{_slug(_normalise_content(label))}"
            found.append(
                (
                    element,
                    Affordance(
                        key=KEY_ALIASES.get(key, key),
                        kind="content",
                        tag=element.tag,
                        label=label,
                    ),
                )
            )

    return found
