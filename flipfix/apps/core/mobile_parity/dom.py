"""A minimal, strict HTML tree for the parity audit.

``html.parser`` is lenient by design: it happily accepts unbalanced markup and
leaves you with a tree that silently disagrees with what a browser would build.
The parity audit walks *ancestor chains* to decide visibility, so a wrong tree
means a wrong answer rather than an obvious crash.

This module therefore applies the small set of implied-end-tag rules the project
templates actually rely on and raises :class:`MalformedHtmlError` on anything
else. The templates are djlint-formatted, so a failure here means a real markup
bug worth fixing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

#: Elements that never have a closing tag.
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

#: Tags implicitly closed by the start of another tag: ``{start: {closes}}``.
AUTO_CLOSE: dict[str, frozenset[str]] = {
    "li": frozenset({"li"}),
    "dt": frozenset({"dt", "dd"}),
    "dd": frozenset({"dt", "dd"}),
    "tr": frozenset({"tr", "td", "th"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "option": frozenset({"option"}),
    "optgroup": frozenset({"option", "optgroup"}),
    "tbody": frozenset({"thead", "tbody", "tr", "td", "th"}),
    "tfoot": frozenset({"thead", "tbody", "tr", "td", "th"}),
}

#: Block-level starts that implicitly close an open ``<p>``.
_P_CLOSERS = frozenset(
    {
        "address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset",
        "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul",
    }
)  # fmt: skip


#: Elements whose text content is code, not document text. ``html.parser``
#: delivers their bodies through ``handle_data`` like any other text, which
#: would otherwise fold JavaScript into an ancestor's accessible name.
RAW_TEXT_TAGS = frozenset({"script", "style"})

#: Elements whose closing tag may legitimately be left out.
OPTIONAL_END_TAGS = frozenset({"p", "li", "dt", "dd", "option", "tr", "td", "th", "tbody"})


class MalformedHtmlError(Exception):
    """The rendered HTML does not nest cleanly enough to trust ancestor chains."""


@dataclass
class Element:
    """One node of the parsed document."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    line: int = 0
    parent: Element | None = field(default=None, repr=False)
    children: list[Element] = field(default_factory=list, repr=False)
    text_parts: list[str] = field(default_factory=list, repr=False)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").split())

    @property
    def is_aria_hidden(self) -> bool:
        return self.attrs.get("aria-hidden") == "true"

    def ancestors(self) -> list[Element]:
        """Self first, then each parent up to the root."""
        chain: list[Element] = []
        node: Element | None = self
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain

    def descendants(self) -> list[Element]:
        out: list[Element] = []
        stack = list(reversed(self.children))
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(node.children))
        return out

    def text(self, *, skip_aria_hidden: bool = True) -> str:
        """Concatenated descendant text.

        ``.visually-hidden`` spans are *included* — that is how ``{% icon %}``
        supplies an accessible name — while ``aria-hidden`` subtrees (the icon
        glyph itself) are excluded.
        """
        if skip_aria_hidden and self.is_aria_hidden:
            return ""
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text(skip_aria_hidden=skip_aria_hidden))
        return " ".join(part for part in parts if part)

    def find_by_id(self, element_id: str) -> Element | None:
        for node in self.descendants():
            if node.attrs.get("id") == element_id:
                return node
        return None


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element(tag="#document")
        self._stack: list[Element] = [self.root]

    @property
    def _open(self) -> Element:
        return self._stack[-1]

    def _close_implied(self, tag: str) -> None:
        closers = AUTO_CLOSE.get(tag, frozenset())
        while len(self._stack) > 1 and self._open.tag in closers:
            self._stack.pop()
        if tag in _P_CLOSERS:
            while len(self._stack) > 1 and self._open.tag == "p":
                self._stack.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._close_implied(tag)
        line, _ = self.getpos()
        element = Element(
            tag=tag,
            attrs={name: (value or "") for name, value in attrs},
            line=line,
            parent=self._open,
        )
        self._open.children.append(element)
        if tag not in VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._close_implied(tag)
        line, _ = self.getpos()
        element = Element(
            tag=tag,
            attrs={name: (value or "") for name, value in attrs},
            line=line,
            parent=self._open,
        )
        self._open.children.append(element)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        line, _ = self.getpos()
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag != tag:
                continue
            # Closing over elements that are still open means the markup does
            # not nest. Silently discarding them would leave the ancestor chain
            # disagreeing with what a browser builds, and the audit reads that
            # chain to decide visibility.
            straddled = [
                node.tag for node in self._stack[depth + 1 :] if node.tag not in OPTIONAL_END_TAGS
            ]
            if straddled:
                raise MalformedHtmlError(
                    f"line {line}: </{tag}> closes over still-open {straddled}."
                )
            del self._stack[depth:]
            return
        raise MalformedHtmlError(f"line {line}: closing </{tag}> with no matching open tag.")

    def unclosed_tags(self) -> list[str]:
        """Tags still open when the document ended, ignoring optional-end-tag ones."""
        return [element.tag for element in self._stack[1:] if element.tag not in OPTIONAL_END_TAGS]

    def handle_data(self, data: str) -> None:
        if self._open.tag in RAW_TEXT_TAGS:
            return
        stripped = " ".join(data.split())
        if stripped:
            self._open.text_parts.append(stripped)


def parse_document(html: str) -> Element:
    """Parse ``html`` into an :class:`Element` tree.

    Raises:
        MalformedHtmlError: on markup that will not nest reliably.
    """
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    unclosed = builder.unclosed_tags()
    if unclosed:
        raise MalformedHtmlError(f"unclosed tags at end of document: {unclosed}")
    return builder.root
