"""Cross-record link registry, conversion, rendering, and reference syncing.

This module provides a plugin-based system for [[type:ref]] markdown links.
Each Django app registers its link types in AppConfig.ready() — core has zero
imports from other apps.

Link formats:
- Slug-based (authoring): [[page:path]], [[machine:slug]], [[model:slug]]
- Slug-based (storage): [[page:id:N]], [[machine:id:N]], [[model:id:N]]
- ID-based (same in both): [[problem:N]], [[log:N]], [[partrequest:N]], [[partrequestupdate:N]]

Public API:
- register(), clear_registry(), LinkType  — registration
- convert_authoring_to_storage()         — on save
- convert_storage_to_authoring()         — on edit load
- sync_references()                       — on save
- render_all_links()                      — in render_markdown template filter
- save_inline_markdown_field()             — for inline AJAX text edits
- link_preview()                          — for label truncation
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

# ---------------------------------------------------------------------------
# LinkType dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkType:
    """Configuration for one link type (e.g., 'machine', 'problem').

    Most fields have defaults so only irregular types need overrides.
    """

    # --- Identity ---
    name: str  # The string in [[name:...]]
    model_path: str  # "catalog.MachineInstance" — resolved via apps.get_model()
    label: str = ""  # Human-readable name for type picker (e.g., "Machine")
    description: str = ""  # Brief description (e.g., "Link to a machine")

    # --- Slug-based vs ID-based ---
    # If set, this type uses [[name:slug]] authoring / [[name:id:N]] storage.
    # The value is the model field containing the slug (e.g., "slug").
    # If None, this type is ID-based: [[name:N]] same in both formats.
    slug_field: str | None = None

    # --- Rendering ---
    url_name: str = ""  # URL pattern name for reverse()
    url_kwarg: str = "pk"  # kwarg name for reverse()
    url_field: str = "pk"  # model field to get the kwarg value
    label_field: str = "name"  # model field for link text (simple cases)
    get_url: Callable[[Any], str] | None = None  # override for irregular URL
    get_label: Callable[[Any], str] | None = None  # override for irregular label
    select_related: tuple[str, ...] = ()

    # --- Authoring format (slug-based types only) ---
    # Custom lookup for authoring format: (model_class, raw_values) -> {key: obj}
    # Default for slug-based types: filter(**{slug_field + "__in": values})
    # Wiki pages override this for tag/slug path parsing.
    authoring_lookup: Callable[[type[models.Model], list[str]], dict[str, Any]] | None = None
    # Custom key derivation for storage-to-authoring: (obj) -> authoring_key
    # Default: getattr(obj, slug_field)
    # Wiki pages override to produce "tag/slug" paths.
    get_authoring_key: Callable[[Any], str] | None = None

    # --- Autocomplete ---
    autocomplete_search_fields: tuple[str, ...] = ()
    autocomplete_ordering: tuple[str, ...] = ()
    autocomplete_select_related: tuple[str, ...] = ()
    autocomplete_serialize: Callable[[Any], dict] | None = None

    # --- Runtime toggle (evaluated at usage time, not registration time) ---
    is_enabled: Callable[[], bool] = field(default=lambda: True)

    # --- Display order in type picker (lower = higher in list) ---
    sort_order: int = 100

    def get_model(self) -> type[Any]:
        """Resolve the model class lazily via Django's app registry."""
        from django.apps import apps

        return apps.get_model(self.model_path)

    def resolve_url(self, obj: Any) -> str:
        """Resolve the URL for a linked object."""
        if self.get_url:
            return self.get_url(obj)
        from django.urls import reverse

        kwarg_value = getattr(obj, self.url_field)
        return reverse(self.url_name, kwargs={self.url_kwarg: kwarg_value})

    def resolve_label(self, obj: Any) -> str:
        """Resolve the display label for a linked object."""
        if self.get_label:
            return self.get_label(obj)
        return str(getattr(obj, self.label_field, obj))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, LinkType] = {}
_patterns: dict[str, dict[str, re.Pattern[str]]] = {}


def register(link_type: LinkType) -> None:
    """Register a link type. Called from each app's AppConfig.ready()."""
    if link_type.name in _registry:
        raise ValueError(f"Link type '{link_type.name}' is already registered")
    _registry[link_type.name] = link_type
    # Compile regex patterns eagerly
    name = re.escape(link_type.name)
    if link_type.slug_field is not None:
        _patterns[link_type.name] = {
            "storage": re.compile(rf"\[\[{name}:id:(\d+)\]\]"),
            "authoring": re.compile(rf"\[\[{name}:(?!id:)([^\]]+)\]\]"),
        }
    else:
        _patterns[link_type.name] = {
            "id": re.compile(rf"\[\[{name}:(\d+)\]\]"),
        }


def clear_registry() -> None:
    """Reset registry state. For tests only."""
    _registry.clear()
    _patterns.clear()


def get_link_type(name: str) -> LinkType | None:
    """Get a registered link type by name, or None."""
    return _registry.get(name)


def get_enabled_link_types() -> list[LinkType]:
    """Return all currently enabled link types."""
    return [lt for lt in _registry.values() if lt.is_enabled()]


def get_autocomplete_types() -> list[dict[str, str]]:
    """Return enabled link types that support autocomplete, for the type picker API."""
    types = [lt for lt in _registry.values() if lt.is_enabled() and lt.autocomplete_serialize]
    types.sort(key=lambda lt: lt.sort_order)
    return [{"name": lt.name, "label": lt.label, "description": lt.description} for lt in types]


def get_enabled_slug_types() -> list[LinkType]:
    """Return enabled link types that use slug-based format."""
    return [lt for lt in get_enabled_link_types() if lt.slug_field is not None]


def get_patterns(link_type: LinkType) -> dict[str, re.Pattern[str]]:
    """Get compiled regex patterns for a link type."""
    return _patterns[link_type.name]


# ---------------------------------------------------------------------------
# Rendering (runs BEFORE markdown processing)
# ---------------------------------------------------------------------------


def render_all_links(text: str) -> str:
    """Convert all [[type:ref]] links in text to markdown links.

    Handles both storage format (primary path) and authoring format
    (defense-in-depth for unconverted content).

    Missing targets render as "*[broken link]*".
    """
    for lt in get_enabled_link_types():
        pats = get_patterns(lt)
        if lt.slug_field is not None:
            text = _render_by_id(text, lt, pats["storage"])
            text = _render_by_slug(text, lt, pats["authoring"])
        else:
            text = _render_by_id(text, lt, pats["id"])
    return text


def _render_by_id(text: str, lt: LinkType, pattern: re.Pattern[str]) -> str:
    """Render [[type:id:N]] or [[type:N]] links by batch PK lookup."""
    matches = list(pattern.finditer(text))
    if not matches:
        return text

    model = lt.get_model()
    ids = [int(m.group(1)) for m in matches]
    qs = model.objects.filter(pk__in=ids)
    if lt.select_related:
        qs = qs.select_related(*lt.select_related)
    by_id = {obj.pk: obj for obj in qs}

    result = text
    for match in reversed(matches):
        obj_id = int(match.group(1))
        obj = by_id.get(obj_id)
        if obj:
            url = lt.resolve_url(obj)
            label = lt.resolve_label(obj)
            result = result[: match.start()] + f"[{label}]({url})" + result[match.end() :]
        else:
            result = result[: match.start()] + "*[broken link]*" + result[match.end() :]
    return result


def _render_by_slug(text: str, lt: LinkType, pattern: re.Pattern[str]) -> str:
    """Render [[type:slug]] links by batch slug lookup (defense-in-depth)."""
    matches = list(pattern.finditer(text))
    if not matches:
        return text

    model = lt.get_model()
    raw_values = [m.group(1) for m in matches]

    if lt.slug_field is None:
        raise ValueError(f"LinkType '{lt.name}' is not slug-based")
    by_key: dict[str, Any]
    if lt.authoring_lookup:
        by_key = lt.authoring_lookup(model, raw_values)
    else:
        qs = model.objects.filter(**{f"{lt.slug_field}__in": raw_values})
        if lt.select_related:
            qs = qs.select_related(*lt.select_related)
        by_key = {getattr(obj, lt.slug_field): obj for obj in qs}

    result = text
    for match in reversed(matches):
        key = match.group(1)
        obj = by_key.get(key)
        if obj:
            url = lt.resolve_url(obj)
            label = lt.resolve_label(obj)
            result = result[: match.start()] + f"[{label}]({url})" + result[match.end() :]
        else:
            result = result[: match.start()] + "*[broken link]*" + result[match.end() :]
    return result


# ---------------------------------------------------------------------------
# Authoring ↔ Storage conversion
# ---------------------------------------------------------------------------


def convert_authoring_to_storage(content: str) -> str:
    """Convert authoring format links to storage format.

    Only affects slug-based types; ID-based types are already in storage format.

    Raises:
        ValidationError: If any linked target doesn't exist
    """
    if not content:
        return content

    errors: list[str] = []
    for lt in get_enabled_slug_types():
        pats = get_patterns(lt)
        content = _convert_to_storage(content, lt, pats["authoring"], errors)

    if errors:
        raise ValidationError(errors)
    return content


def _convert_to_storage(
    content: str,
    lt: LinkType,
    pattern: re.Pattern[str],
    errors: list[str],
) -> str:
    """Convert [[type:slug]] to [[type:id:N]] for one link type."""
    matches = list(pattern.finditer(content))
    if not matches:
        return content

    model = lt.get_model()
    raw_values = [m.group(1) for m in matches]

    if lt.slug_field is None:
        raise ValueError(f"LinkType '{lt.name}' is not slug-based")
    by_key: dict[str, Any]
    if lt.authoring_lookup:
        by_key = lt.authoring_lookup(model, raw_values)
    else:
        qs = model.objects.filter(**{f"{lt.slug_field}__in": raw_values})
        by_key = {getattr(obj, lt.slug_field): obj for obj in qs}

    result = content
    for match in reversed(matches):
        key = match.group(1)
        obj = by_key.get(key)
        if obj:
            result = result[: match.start()] + f"[[{lt.name}:id:{obj.pk}]]" + result[match.end() :]
        else:
            errors.append(f"{lt.name.title()} not found: [[{lt.name}:{key}]]")
            result = result[: match.start()] + match.group(0) + result[match.end() :]
    return result


def convert_storage_to_authoring(content: str) -> str:
    """Convert storage format links to authoring format for editing.

    Only affects slug-based types; ID-based types are the same in both formats.
    """
    if not content:
        return content

    for lt in get_enabled_slug_types():
        pats = get_patterns(lt)
        content = _convert_to_authoring(content, lt, pats["storage"])
    return content


def _convert_to_authoring(
    content: str,
    lt: LinkType,
    pattern: re.Pattern[str],
) -> str:
    """Convert [[type:id:N]] to [[type:slug]] for one link type."""
    if lt.slug_field is None:
        raise ValueError(f"LinkType '{lt.name}' is not slug-based")
    matches = list(pattern.finditer(content))
    if not matches:
        return content

    model = lt.get_model()
    ids = [int(m.group(1)) for m in matches]
    by_id = {obj.pk: obj for obj in model.objects.filter(pk__in=ids)}

    result = content
    for match in reversed(matches):
        obj_id = int(match.group(1))
        obj = by_id.get(obj_id)
        if obj:
            if lt.get_authoring_key:
                key = lt.get_authoring_key(obj)
            else:
                key = getattr(obj, lt.slug_field)
            result = result[: match.start()] + f"[[{lt.name}:{key}]]" + result[match.end() :]
        else:
            # Keep storage format for broken links (target deleted)
            result = result[: match.start()] + match.group(0) + result[match.end() :]
    return result


# ---------------------------------------------------------------------------
# Reference syncing
# ---------------------------------------------------------------------------


def sync_references(source: models.Model, content: str) -> None:
    """Sync RecordReference table based on links found in content.

    Compares current links in content against existing RecordReference rows
    for this source, then batch-creates/deletes the diff.

    Args:
        source: The model instance containing the markdown
        content: The markdown content in storage format
    """
    from django.contrib.contenttypes.models import ContentType

    from the_flip.apps.core.models import RecordReference

    content = content or ""

    # Parse all link IDs from content using registered patterns
    links_by_model: dict[type[Any], set[int]] = {}
    for lt in get_enabled_link_types():
        pats = get_patterns(lt)
        pattern = pats.get("storage") or pats.get("id")
        if pattern is None:
            continue
        ids = {int(m.group(1)) for m in pattern.finditer(content)}
        links_by_model[lt.get_model()] = ids

    if not links_by_model:
        return

    # Pre-compute all ContentTypes (single query via get_for_models)
    source_ct = ContentType.objects.get_for_model(source)
    content_types = ContentType.objects.get_for_models(*links_by_model.keys())

    # Get existing references for this source
    existing_refs = RecordReference.objects.filter(
        source_type=source_ct, source_id=source.pk
    ).values_list("target_type_id", "target_id")
    existing_by_ct: dict[int, set[int]] = {}
    for ct_id, target_id in existing_refs:
        existing_by_ct.setdefault(ct_id, set()).add(target_id)

    to_create: list[RecordReference] = []
    to_delete_filters: list[Q] = []

    for model_class, target_ids in links_by_model.items():
        target_ct = content_types[model_class]
        existing_ids = existing_by_ct.get(target_ct.id, set())

        if not target_ids:
            # No links of this type — clean up any stale references
            if existing_ids:
                to_delete_filters.append(Q(target_type=target_ct, target_id__in=existing_ids))
            continue

        # Only reference targets that actually exist
        valid_ids = set(model_class.objects.filter(pk__in=target_ids).values_list("pk", flat=True))

        # Refs to add
        for target_id in valid_ids - existing_ids:
            to_create.append(
                RecordReference(
                    source_type=source_ct,
                    source_id=source.pk,
                    target_type=target_ct,
                    target_id=target_id,
                )
            )

        # Refs to remove
        ids_to_remove = existing_ids - target_ids
        if ids_to_remove:
            to_delete_filters.append(Q(target_type=target_ct, target_id__in=ids_to_remove))

    # Batch operations
    if to_delete_filters:
        delete_q = to_delete_filters[0]
        for q in to_delete_filters[1:]:
            delete_q |= q
        RecordReference.objects.filter(source_type=source_ct, source_id=source.pk).filter(
            delete_q
        ).delete()

    if to_create:
        RecordReference.objects.bulk_create(to_create, ignore_conflicts=True)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def save_inline_markdown_field(
    instance: models.Model,
    field: str,
    raw_text: str,
    *,
    extra_update_fields: Sequence[str] = (),
) -> None:
    """Convert, save, and sync a markdown text field from an inline AJAX edit.

    Converts authoring-format links to storage format, saves the field,
    and syncs the :class:`~the_flip.apps.core.models.RecordReference` table.

    Args:
        extra_update_fields: Additional field names to include in
            ``save(update_fields=...)``, e.g. ``["updated_by"]``.

    Raises :exc:`~django.core.exceptions.ValidationError` if any linked
    targets don't exist.
    """
    text = convert_authoring_to_storage(raw_text) if raw_text else raw_text
    setattr(instance, field, text)
    instance.save(update_fields=[field, "updated_at", *extra_update_fields])
    sync_references(instance, text)


def link_preview(content: str, max_len: int = 30) -> str:
    """Truncate and sanitize text for use inside a markdown link label.

    Strips brackets (which would break ``[label](url)`` syntax) and
    collapses whitespace so the preview reads cleanly inline.
    """
    preview = content.replace("[", "").replace("]", "")
    preview = " ".join(preview.split())
    if len(preview) > max_len:
        preview = preview[:max_len] + "..."
    return preview
