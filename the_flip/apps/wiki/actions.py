"""Wiki template blocks: parsing, extraction, and rendering support.

Template blocks are sections of wiki page content delimited by HTML comment
markers that can be turned into pre-filled create forms (via a button on the
wiki page or a template selector dropdown on create forms).

Syntax::

    <!-- template:start name="intake" -->
    ...visible content...
    <!-- template:end name="intake" -->

    <!-- template:action name="intake" action="button,option" type="problem"
         machine="blackout" label="Start Intake" -->

Markers:
    - ``template:start`` / ``template:end``: delimit content (invisible,
      content renders normally). Only ``name`` is required.
    - ``template:action``: controls how the template reaches users.
      Required attributes: ``name``, ``action``, ``type``, ``label``.
      The ``action`` attribute accepts ``button``, ``option``, or
      ``button,option``.
      Optional: ``machine``, ``location``, ``tags`` (for ``type="page"``),
      ``title`` (for ``type="page"``), ``priority`` (for ``type="problem"``).
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.html import format_html

from the_flip.apps.core.markdown import fenced_code_ranges
from the_flip.apps.maintenance.models import ProblemReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_TEMPLATE_START_RE = re.compile(r'<!--\s*template:start\s+name="(?P<name>[^"]+)"\s*-->')
_TEMPLATE_END_RE = re.compile(r'<!--\s*template:end\s+name="(?P<name>[^"]+)"\s*-->')
_TEMPLATE_ACTION_RE = re.compile(r"<!--\s*template:action\s+(?P<attrs>[^>]*?)\s*-->")
_TEMPLATE_ANY_RE = re.compile(r"<!--\s*template:(?P<kind>\w+)")
_ATTR_RE = re.compile(r'(?P<key>\w+)="(?P<value>[^"]*)"')

_VALID_MARKER_KINDS = {"start", "end", "action"}

# Required attributes on template:action markers
_ACTION_REQUIRED_ATTRS = {"name", "action", "type", "label"}

# Valid individual parts of the action attribute (comma-separated, order-independent)
_VALID_ACTION_PARTS = {"button", "option"}

# Valid priority values for type="problem" — derived from the enum so
# adding/removing priorities in the model automatically updates validation.
_VALID_PRIORITIES = {v for v, _ in ProblemReport.Priority.maintainer_settable()}


# ---------------------------------------------------------------------------
# Fenced code block helpers
# ---------------------------------------------------------------------------


def _in_fence(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def _outside_fences(
    matches: Iterable[re.Match[str]], ranges: list[tuple[int, int]]
) -> list[re.Match[str]]:
    """Filter finditer results to exclude matches inside fenced code blocks."""
    if not ranges:
        return list(matches)
    return [m for m in matches if not _in_fence(m.start(), ranges)]


def _fence_aware_sub(
    regex: re.Pattern[str],
    repl: str | Callable[[re.Match[str]], str],
    content: str,
) -> str:
    """Like regex.sub() but skip matches inside fenced code blocks.

    Computes fence ranges from *content* so positions are always correct,
    even after prior substitutions have shifted offsets.
    """
    ranges = fenced_code_ranges(content)
    if not ranges:
        return regex.sub(repl, content)

    def wrapper(match: re.Match[str]) -> str:
        if _in_fence(match.start(), ranges):
            return match.group()
        return repl(match) if callable(repl) else repl

    return regex.sub(wrapper, content)


# ---------------------------------------------------------------------------
# Record type configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordTypeConfig:
    """Configuration for a record type that can be created from template blocks."""

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
    """Content extracted from template:start/end markers."""

    name: str
    content: str


@dataclass(frozen=True)
class MarkerValidation:
    """Result of structural validation of template start/end markers."""

    content_blocks: list[ContentBlock]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ActionBlock:
    """Fully resolved template: content block + action marker attributes."""

    name: str
    record_type: str
    machine_slug: str
    label: str
    content: str
    action: str = "button"
    location_slug: str = ""
    tags: str = ""
    title: str = ""
    priority: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_attrs(attr_string: str) -> dict[str, str]:
    """Parse key="value" pairs from an attribute string."""
    return {m.group("key"): m.group("value") for m in _ATTR_RE.finditer(attr_string)}


def _validate_action_attrs(attrs: dict[str, str]) -> str | None:
    """Validate template:action attributes, returning an error message or None if valid."""
    missing = _ACTION_REQUIRED_ATTRS - set(attrs.keys())
    if missing:
        return f"missing required attributes: {', '.join(sorted(missing))}"
    action_parts = set(attrs["action"].split(","))
    invalid_parts = action_parts - _VALID_ACTION_PARTS
    if invalid_parts:
        return (
            f"invalid action '{attrs['action']}'"
            f" (each part must be one of {', '.join(sorted(_VALID_ACTION_PARTS))})"
        )
    if attrs["type"] not in _RECORD_TYPES:
        return f"invalid type '{attrs['type']}' (must be one of {', '.join(sorted(_RECORD_TYPES))})"
    priority = attrs.get("priority", "")
    if priority and priority not in _VALID_PRIORITIES:
        return (
            f"invalid priority '{priority}' (must be one of {', '.join(sorted(_VALID_PRIORITIES))})"
        )
    return None


def _make_action_block(attrs: dict[str, str], content: str) -> ActionBlock:
    """Build an ActionBlock from parsed attributes and content."""
    return ActionBlock(
        name=attrs["name"],
        record_type=attrs["type"],
        machine_slug=attrs.get("machine", ""),
        label=attrs["label"],
        content=content,
        action=attrs["action"],
        location_slug=attrs.get("location", ""),
        tags=attrs.get("tags", ""),
        title=attrs.get("title", ""),
        priority=attrs.get("priority", ""),
    )


# ---------------------------------------------------------------------------
# Structural validation (read-only pass on start/end markers only)
# ---------------------------------------------------------------------------


def _validate_markers(content: str) -> MarkerValidation:
    """Validate structural integrity of start/end markers (read-only).

    Checks matching names, nesting, and duplicates.  Does **not** validate
    action attributes — those are checked per-marker in the callers.
    """
    fence_ranges = fenced_code_ranges(content)
    starts = _outside_fences(_TEMPLATE_START_RE.finditer(content), fence_ranges)
    ends = _outside_fences(_TEMPLATE_END_RE.finditer(content), fence_ranges)

    if not starts and not ends:
        return MarkerValidation(content_blocks=[], errors=[])

    # Build ordered list of (position, kind, match) for overlap/nesting check
    markers: list[tuple[int, str, re.Match]] = []
    for m in starts:
        markers.append((m.start(), "start", m))
    for m in ends:
        markers.append((m.start(), "end", m))
    markers.sort(key=lambda t: t[0])

    # Check for structural errors: nesting, unmatched, duplicates
    errors: list[str] = []
    seen_names: set[str] = set()
    open_block: str | None = None
    blocks: dict[str, tuple[re.Match, re.Match]] = {}

    for _pos, kind, match in markers:
        name = match.group("name")
        if kind == "start":
            if name in seen_names:
                errors.append(f"Template '{name}': duplicate name")
            elif open_block is not None:
                errors.append(
                    f"Template '{name}': nested inside '{open_block}' (nesting not allowed)"
                )
            else:
                open_block = name
                blocks[name] = (match, match)  # placeholder until we find end
            seen_names.add(name)
        else:  # end
            if open_block is None or open_block != name:
                errors.append(
                    f"Template '{name}': unmatched template:end (no matching template:start)"
                )
            else:
                blocks[name] = (blocks[name][0], match)
            open_block = None

    if open_block is not None:
        errors.append(f"Template '{open_block}': missing template:end")

    if errors:
        return MarkerValidation(content_blocks=[], errors=errors)

    return MarkerValidation(content_blocks=_build_content_blocks(content, blocks), errors=[])


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
# Author-facing syntax validation (called from form save paths)
# ---------------------------------------------------------------------------


def validate_template_syntax(content: str) -> list[str]:
    """Validate template marker syntax, returning human-readable error messages.

    Checks both structural integrity (start/end pairing) and action attribute
    validity. Returns an empty list when everything is valid.

    Structural checks are delegated to ``_validate_markers`` — single source
    of truth for start/end validation.
    """
    # Check for typos like "template:starts" or "template:star" first —
    # these are likely the root cause of any structural failures downstream.
    fence_ranges = fenced_code_ranges(content)
    unrecognized = sorted(
        {m.group("kind") for m in _outside_fences(_TEMPLATE_ANY_RE.finditer(content), fence_ranges)}
        - _VALID_MARKER_KINDS
    )
    if unrecognized:
        return [
            f"Unrecognized marker 'template:{kind}'"
            f" (valid markers: {', '.join(sorted(_VALID_MARKER_KINDS))})"
            for kind in unrecognized
        ]

    validation = _validate_markers(content)

    # Structural errors cascade — action markers will all fail if the
    # start/end skeleton is broken, producing noisy duplicate messages.
    # Report only structural errors and let the author fix those first.
    if not validation.is_valid:
        return list(validation.errors)

    # --- Action attribute validation ---
    errors: list[str] = []
    matched_names = {b.name for b in validation.content_blocks}
    reported_names: set[str] = set()

    for match in _outside_fences(_TEMPLATE_ACTION_RE.finditer(content), fence_ranges):
        attrs = _parse_attrs(match.group("attrs"))
        name = attrs.get("name", "(unnamed)")

        error = _validate_action_attrs(attrs)
        if error:
            errors.append(f"template:action '{name}': {error}")
            continue

        # Deduplicate: only report "no matching content block" once per name
        if attrs["name"] not in matched_names and attrs["name"] not in reported_names:
            reported_names.add(attrs["name"])
            errors.append(
                f"template:action '{attrs['name']}': no matching content block"
                " (needs template:start/end with the same name)"
            )

    return errors


# ---------------------------------------------------------------------------
# Token substitution (runs only after successful structural validation)
# ---------------------------------------------------------------------------


def prepare_for_rendering(content: str) -> tuple[str, dict[str, ActionBlock]]:
    """Validate markers and prepare content for the markdown pipeline.

    1. Validates start/end structure (atomic — any structural error aborts).
    2. Strips ``template:start`` and ``template:end`` markers (content between
       is kept).
    3. Replaces valid ``template:action`` markers (where ``action`` contains
       "button") with unique alphanumeric tokens. Markers with invalid
       attributes or ``action="option"`` are silently stripped.

    Returns:
        ``(processed_content, token_map)`` where *token_map* maps each
        token string to its ``ActionBlock``.  If structural validation fails,
        returns ``(original_content, {})`` — no partial mutations.
    """
    validation = _validate_markers(content)
    if not validation.is_valid:
        # Structural error — return original content, no buttons
        return content, {}

    if not validation.content_blocks:
        # No content blocks — strip any orphan action markers silently
        result = _fence_aware_sub(_TEMPLATE_ACTION_RE, "", content)
        return result, {}

    blocks_by_name: dict[str, ContentBlock] = {b.name: b for b in validation.content_blocks}

    # Strip start/end markers (content between is preserved)
    result = _fence_aware_sub(_TEMPLATE_START_RE, "", content)
    result = _fence_aware_sub(_TEMPLATE_END_RE, "", result)

    # Replace action markers with tokens (buttons only)
    token_map: dict[str, ActionBlock] = {}

    def _replace_action(match: re.Match) -> str:
        attrs = _parse_attrs(match.group("attrs"))
        name = attrs.get("name", "")

        # Validate attributes
        error = _validate_action_attrs(attrs)
        if error:
            logger.warning("template:action name='%s': %s — skipped", name or "(unnamed)", error)
            return ""

        # Only render buttons (option-only markers are stripped from display)
        if "button" not in attrs["action"]:
            return ""

        # Check matching content block
        cb = blocks_by_name.get(name)
        if cb is None:
            logger.warning(
                "template:action name='%s' has no matching content block — skipped",
                name,
            )
            return ""

        token = secrets.token_hex(16)
        token_map[token] = _make_action_block(attrs, cb.content)
        return token

    result = _fence_aware_sub(_TEMPLATE_ACTION_RE, _replace_action, result)

    return result, token_map


def inject_buttons(html: str, token_map: dict[str, ActionBlock], page_pk: int) -> str:
    """Replace tokens with button HTML after sanitization.

    Uses ``format_html`` / ``conditional_escape`` for the label since it is
    author-controlled content injected *after* nh3 sanitization.
    """
    for token, block in token_map.items():
        url = build_template_url(block, page_pk)
        button_html = format_html(
            '<div class="wiki-template-action">'
            '<a href="{}" class="btn btn--secondary">{}</a>'
            "</div>",
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


def build_template_url(action: ActionBlock, page_pk: int) -> str:
    """Build the URL for the wiki template prefill endpoint."""
    return reverse(
        "wiki-template-prefill",
        kwargs={"page_pk": page_pk, "template_name": action.name},
    )


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
# Content extraction (used by the prefill view and template content API)
# ---------------------------------------------------------------------------


def extract_template_content(content: str, template_name: str) -> ActionBlock | None:
    """Extract a single named template block from page content.

    Assembles an ``ActionBlock`` from the matching content block (start/end)
    and the first ``template:action`` marker with the same name.  If multiple
    action markers share the same name (e.g. one at the top and one at the
    bottom of a long page), only the first is used — all markers for a given
    name should carry identical attributes.

    Returns ``None`` if the content block or action marker doesn't exist,
    attributes are invalid, or structural validation fails.
    """
    validation = _validate_markers(content)
    if not validation.is_valid:
        return None

    # Find content block by name
    cb = None
    for block in validation.content_blocks:
        if block.name == template_name:
            cb = block
            break
    if cb is None:
        return None

    # Find first action marker with matching name (outside code fences)
    fence_ranges = fenced_code_ranges(content)
    for match in _outside_fences(_TEMPLATE_ACTION_RE.finditer(content), fence_ranges):
        attrs = _parse_attrs(match.group("attrs"))
        if attrs.get("name") != template_name:
            continue
        error = _validate_action_attrs(attrs)
        if error:
            return None
        return _make_action_block(attrs, cb.content)

    # No action marker found for this name
    return None


# ---------------------------------------------------------------------------
# Template option index sync
# ---------------------------------------------------------------------------


@dataclass
class TemplateSyncResult:
    """Summary of what ``sync_template_option_index`` changed."""

    registered: list[ActionBlock] = field(default_factory=list)
    removed_count: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.registered) or self.removed_count > 0


def _parse_option_blocks(content: str) -> list[ActionBlock]:
    """Parse template:action markers where ``action`` contains "option".

    Validates structure, then collects option-eligible ActionBlocks.
    Deduplicates by name (first occurrence wins).
    """
    validation = _validate_markers(content)
    if not validation.is_valid:
        return []

    blocks_by_name = {b.name: b for b in validation.content_blocks}
    fence_ranges = fenced_code_ranges(content)
    seen_names: set[str] = set()
    result: list[ActionBlock] = []

    for match in _outside_fences(_TEMPLATE_ACTION_RE.finditer(content), fence_ranges):
        attrs = _parse_attrs(match.group("attrs"))
        name = attrs.get("name", "")

        # Skip duplicates
        if name in seen_names:
            continue

        # Validate
        error = _validate_action_attrs(attrs)
        if error:
            continue

        # Only index markers where action contains "option"
        if "option" not in attrs["action"]:
            continue

        # Must have a matching content block
        cb = blocks_by_name.get(name)
        if cb is None:
            continue

        seen_names.add(name)
        result.append(_make_action_block(attrs, cb.content))

    return result


def sync_template_option_index(page) -> TemplateSyncResult:
    """Rebuild the ``TemplateOptionIndex`` for a wiki page.

    Deletes all existing rows for the page, then creates new rows from
    ``template:action`` markers where ``action`` contains "option".

    Args:
        page: A saved ``WikiPage`` instance.

    Returns:
        A ``TemplateSyncResult`` summarising what changed.
    """
    from django.db import transaction

    from the_flip.apps.wiki.models import TemplateOptionIndex

    # Parse new option blocks
    option_blocks = _parse_option_blocks(page.content)

    with transaction.atomic():
        # Delete existing rows
        old_count = TemplateOptionIndex.objects.filter(page=page).delete()[0]

        if option_blocks:
            TemplateOptionIndex.objects.bulk_create(
                [
                    TemplateOptionIndex(
                        page=page,
                        template_name=block.name,
                        record_type=block.record_type,
                        machine_slug=block.machine_slug,
                        location_slug=block.location_slug,
                        priority=block.priority,
                        label=block.label,
                    )
                    for block in option_blocks
                ]
            )

    # removed_count = rows that existed before but aren't in the new set
    removed_count = max(0, old_count - len(option_blocks))

    return TemplateSyncResult(
        registered=option_blocks,
        removed_count=removed_count,
    )
