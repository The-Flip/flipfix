"""Decide whether an element is displayed at a given viewport width."""

from __future__ import annotations

from dataclasses import dataclass

from flipfix.apps.core.mobile_parity.config import NON_VIEWPORT_HIDDEN_CLASSES
from flipfix.apps.core.mobile_parity.css_rules import DisplayIndex, DisplayRule
from flipfix.apps.core.mobile_parity.dom import Element


@dataclass(frozen=True)
class Concealment:
    """Why an element is not displayed at some width."""

    rule: DisplayRule
    #: The element actually carrying the hiding class — self or an ancestor.
    at_tag: str

    @property
    def class_name(self) -> str:
        return self.rule.class_name

    @property
    def selector(self) -> str:
        return f".{self.rule.class_name}"


def concealment(element: Element, index: DisplayIndex, width: int) -> Concealment | None:
    """Return what hides ``element`` at ``width``, or ``None`` if it is shown.

    ``display: none`` on an ancestor removes the whole subtree, so the ancestor
    chain is walked from the element upwards and the first hiding rule wins.

    Interaction-state classes are stripped first: a collapsed dropdown hides its
    contents at *every* width, which is a JS state rather than a parity gap.
    """
    for node in element.ancestors():
        classes = node.classes - NON_VIEWPORT_HIDDEN_CLASSES
        if not classes:
            continue
        rule = index.winning_rule(classes, width)
        if rule is not None and rule.is_hidden:
            return Concealment(rule=rule, at_tag=node.tag)
    return None


def is_visible(element: Element, index: DisplayIndex, width: int) -> bool:
    return concealment(element, index, width) is None
