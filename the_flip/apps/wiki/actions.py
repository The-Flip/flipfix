"""Wiki action blocks: parsing, extraction, and rendering support.

Action blocks are sections of wiki page content delimited by HTML comment
markers that can be turned into pre-filled create forms via a button click.

Syntax::

    <!-- action:start name="intake" -->
    ...visible content...
    <!-- action:end name="intake" -->

    <!-- action:button name="intake" type="problem" machine="blackout" label="Start Intake" -->

Markers:
    - ``action:start`` / ``action:end``: delimit content (invisible, content renders normally).
      Only ``name`` is required.
    - ``action:button``: renders a button wherever placed (independent of content markers).
      Carries the action attributes: ``name``, ``type``, ``label`` (required),
      ``machine`` (optional), ``tags`` (optional, for ``type="page"``),
      ``title`` (optional, for ``type="page"``).
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass

from django.urls import reverse
from django.utils.html import format_html

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_ACTION_START_RE = re.compile(r'<!--\s*action:start\s+name="(?P<name>[^"]+)"\s*-->')
_ACTION_END_RE = re.compile(r'<!--\s*action:end\s+name="(?P<name>[^"]+)"\s*-->')
_ACTION_BUTTON_RE = re.compile(r"<!--\s*action:button\s+(?P<attrs>[^>]*?)\s*-->")
_ATTR_RE = re.compile(r'(?P<key>\w+)="(?P<value>[^"]*)"')

# Required attributes on action:button markers
_BUTTON_REQUIRED_ATTRS = {"name", "type", "label"}


# ---------------------------------------------------------------------------
# Record type configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordTypeConfig:
    """Configuration for a record type that can be created from action blocks."""

    machine_url_name: str
    global_url_name: str
    prefill_field: str


_RECORD_TYPES: dict[str, RecordTypeConfig] = {
    "problem": RecordTypeConfig(
        machine_url_name="problem-report-create-machine",
        global_url_name="problem-report-create",
        prefill_field="description",
    ),
    "log": RecordTypeConfig(
        machine_url_name="log-create-machine",
        global_url_name="log-create-global",
        prefill_field="text",
    ),
    "partrequest": RecordTypeConfig(
        machine_url_name="part-request-create-machine",
        global_url_name="part-request-create",
        prefill_field="text",
    ),
    "page": RecordTypeConfig(
        machine_url_name="",  # Wiki pages are not machine-scoped
        global_url_name="wiki-page-create",
        prefill_field="content",
    ),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentBlock:
    """Content extracted from action:start/end markers."""

    name: str
    content: str


@dataclass(frozen=True)
class ActionBlock:
    """Fully resolved action: content block + button attributes."""

    name: str
    record_type: str
    machine_slug: str
    label: str
    content: str
    tags: str = ""
    title: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_attrs(attr_string: str) -> dict[str, str]:
    """Parse key="value" pairs from an attribute string."""
    return {m.group("key"): m.group("value") for m in _ATTR_RE.finditer(attr_string)}


def _validate_button_attrs(attrs: dict[str, str]) -> str | None:
    """Validate button attributes, returning an error message or None if valid."""
    missing = _BUTTON_REQUIRED_ATTRS - set(attrs.keys())
    if missing:
        return f"missing required attributes: {', '.join(sorted(missing))}"
    if attrs["type"] not in _RECORD_TYPES:
        return f"invalid type '{attrs['type']}' (must be one of {', '.join(sorted(_RECORD_TYPES))})"
    return None


# ---------------------------------------------------------------------------
# Structural validation (read-only pass on start/end markers only)
# ---------------------------------------------------------------------------


def _validate_markers(content: str) -> list[ContentBlock] | None:
    """Validate structural integrity of start/end markers (read-only).

    Checks matching names, nesting, and duplicates.  Does **not** validate
    button attributes — those are checked per-button in the callers.

    Returns a list of ``ContentBlock`` objects if all markers are structurally
    valid, or ``None`` if any error is found (caller should fall back to
    rendering original content unchanged).
    """
    starts = list(_ACTION_START_RE.finditer(content))
    ends = list(_ACTION_END_RE.finditer(content))

    if not starts and not ends:
        return []

    # Build ordered list of (position, kind, match) for overlap/nesting check
    markers: list[tuple[int, str, re.Match]] = []
    for m in starts:
        markers.append((m.start(), "start", m))
    for m in ends:
        markers.append((m.start(), "end", m))
    markers.sort(key=lambda t: t[0])

    # Check for structural errors: nesting, unmatched, duplicates
    seen_names: set[str] = set()
    open_block: str | None = None
    blocks: dict[str, tuple[re.Match, re.Match]] = {}

    for _pos, kind, match in markers:
        if kind == "start":
            name = match.group("name")

            # Check for duplicate names
            if name in seen_names:
                logger.error("Action block '%s': duplicate name", name)
                return None
            seen_names.add(name)

            # Check nesting
            if open_block is not None:
                logger.error(
                    "Action block '%s': nested inside '%s'",
                    name,
                    open_block,
                )
                return None

            open_block = name
            blocks[name] = (match, match)  # placeholder until we find end

        else:  # end
            name = match.group("name")
            if open_block is None or open_block != name:
                logger.error(
                    "Action block '%s': unmatched action:end",
                    name,
                )
                return None
            # Store the actual start/end pair
            blocks[name] = (blocks[name][0], match)
            open_block = None

    # Any unclosed block
    if open_block is not None:
        logger.error("Action block '%s': missing action:end", open_block)
        return None

    return _build_content_blocks(content, blocks)


def _build_content_blocks(
    content: str, blocks: dict[str, tuple[re.Match, re.Match]]
) -> list[ContentBlock]:
    """Build ContentBlock objects from validated start/end match pairs."""
    return [
        ContentBlock(
            name=start_match.group("name"),
            content=content[start_match.end() : end_match.start()],
        )
        for start_match, end_match in blocks.values()
    ]


# ---------------------------------------------------------------------------
# Token substitution (runs only after successful structural validation)
# ---------------------------------------------------------------------------


def prepare_for_rendering(content: str) -> tuple[str, dict[str, ActionBlock]]:
    """Validate markers and prepare content for the markdown pipeline.

    1. Validates start/end structure (atomic — any structural error aborts).
    2. Strips ``action:start`` and ``action:end`` markers (content between is kept).
    3. Replaces valid ``action:button`` markers with unique alphanumeric tokens.
       Buttons with invalid attributes are silently skipped (warning logged).

    Returns:
        ``(processed_content, token_map)`` where *token_map* maps each
        token string to its ``ActionBlock``.  If structural validation fails,
        returns ``(original_content, {})`` — no partial mutations.
    """
    content_blocks = _validate_markers(content)
    if content_blocks is None:
        # Structural error — return original content, no buttons
        return content, {}

    if not content_blocks:
        # No content blocks — strip any orphan button markers silently
        result = _ACTION_BUTTON_RE.sub("", content)
        return result, {}

    blocks_by_name: dict[str, ContentBlock] = {b.name: b for b in content_blocks}

    # Strip start/end markers (content between is preserved)
    result = _ACTION_START_RE.sub("", content)
    result = _ACTION_END_RE.sub("", result)

    # Replace button markers with tokens
    token_map: dict[str, ActionBlock] = {}

    def _replace_button(match: re.Match) -> str:
        attrs = _parse_attrs(match.group("attrs"))
        name = attrs.get("name", "")

        # Validate button attributes
        error = _validate_button_attrs(attrs)
        if error:
            logger.warning("action:button name='%s': %s — skipped", name or "(unnamed)", error)
            return ""

        # Check matching content block
        cb = blocks_by_name.get(name)
        if cb is None:
            logger.warning(
                "action:button name='%s' has no matching content block — skipped",
                name,
            )
            return ""

        token = secrets.token_hex(16)
        token_map[token] = ActionBlock(
            name=name,
            record_type=attrs["type"],
            machine_slug=attrs.get("machine", ""),
            label=attrs["label"],
            content=cb.content,
            tags=attrs.get("tags", ""),
            title=attrs.get("title", ""),
        )
        return token

    result = _ACTION_BUTTON_RE.sub(_replace_button, result)

    return result, token_map


def inject_buttons(html: str, token_map: dict[str, ActionBlock], page_pk: int) -> str:
    """Replace tokens with button HTML after sanitization.

    Uses ``format_html`` / ``conditional_escape`` for the label since it is
    author-controlled content injected *after* nh3 sanitization.
    """
    for token, block in token_map.items():
        url = build_action_url(block, page_pk)
        button_html = format_html(
            '<div class="wiki-action"><a href="{}" class="btn btn--secondary">{}</a></div>',
            url,
            block.label,
        )
        # Strip <p> wrapper if markdown wrapped the standalone token in a paragraph,
        # which would produce invalid <p><div>…</div></p>.
        html = re.sub(rf"<p>\s*{re.escape(token)}\s*</p>", button_html, html)
        html = html.replace(token, button_html)
    return html


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def build_action_url(action: ActionBlock, page_pk: int) -> str:
    """Build the URL for the wiki action prefill endpoint."""
    return reverse("wiki-action-prefill", kwargs={"page_pk": page_pk, "action_name": action.name})


def get_prefill_field(record_type: str) -> str:
    """Return the form field name to pre-fill for a record type."""
    return _RECORD_TYPES[record_type].prefill_field


def build_create_url(action: ActionBlock) -> str:
    """Build the URL for the target create form.

    Returns a machine-scoped URL if ``machine_slug`` is set, otherwise global.
    """
    config = _RECORD_TYPES[action.record_type]
    if action.machine_slug and config.machine_url_name:
        return reverse(config.machine_url_name, kwargs={"slug": action.machine_slug})
    return reverse(config.global_url_name)


# ---------------------------------------------------------------------------
# Content extraction (used by the prefill view)
# ---------------------------------------------------------------------------


def extract_action_content(content: str, action_name: str) -> ActionBlock | None:
    """Extract a single named action block from page content.

    Assembles an ``ActionBlock`` from the matching content block (start/end)
    and the first button marker with the same name.  If multiple buttons
    share the same name (e.g. one at the top and one at the bottom of a
    long page), only the first is used — all buttons for a given name
    should carry identical attributes.

    Returns ``None`` if the content block or button doesn't exist,
    button attributes are invalid, or structural validation fails.
    """
    content_blocks = _validate_markers(content)
    if content_blocks is None:
        return None

    # Find content block by name
    cb = None
    for block in content_blocks:
        if block.name == action_name:
            cb = block
            break
    if cb is None:
        return None

    # Find first button with matching name
    for match in _ACTION_BUTTON_RE.finditer(content):
        attrs = _parse_attrs(match.group("attrs"))
        if attrs.get("name") != action_name:
            continue
        error = _validate_button_attrs(attrs)
        if error:
            return None
        return ActionBlock(
            name=action_name,
            record_type=attrs["type"],
            machine_slug=attrs.get("machine", ""),
            label=attrs["label"],
            content=cb.content,
            tags=attrs.get("tags", ""),
            title=attrs.get("title", ""),
        )

    # No button found for this name
    return None
