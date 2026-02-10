"""Wiki views."""

from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from the_flip.apps.core.markdown_links import save_inline_markdown_field
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin, FormPrefillMixin

from .actions import (
    TemplateSyncResult,
    build_create_url,
    extract_template_content,
    get_prefill_field,
    sync_template_option_index,
    validate_template_syntax,
)
from .forms import WikiPageForm
from .models import UNTAGGED_SENTINEL, TemplateOptionIndex, WikiPage, WikiPageTag, WikiTagOrder
from .selectors import build_nav_tree


def _add_template_sync_toast(request, result: TemplateSyncResult) -> None:
    """Add a Django messages toast if template registrations changed."""
    if not result.changed:
        return

    if result.registered:
        links = format_html_join(
            ", ",
            '<a href="{}">{}</a>',
            ((build_create_url(block), block.label) for block in result.registered),
        )
        count = len(result.registered)
        noun = "template" if count == 1 else "templates"
        msg = format_html("{} {} registered: {}", count, noun, links)
    else:
        msg = format_html("Templates removed from index.")

    messages.info(request, msg)


def parse_wiki_path(path: str) -> tuple[str, str]:
    """Parse a wiki URL path into (tag, slug).

    The path is everything after /wiki/doc/. The last segment is always the slug,
    everything before is the tag (joined by '/'), or empty string for untagged pages.

    Examples:
        'overview' -> ('', 'overview')
        'machines/overview' -> ('machines', 'overview')
        'machines/blackout/system-6' -> ('machines/blackout', 'system-6')
    """
    if not path:
        raise Http404("Empty path")

    # Strip trailing slash if present
    path = path.rstrip("/")

    segments = path.split("/")
    slug = segments[-1]
    tag = "/".join(segments[:-1])  # Empty string if only one segment

    return tag, slug


class WikiPagePathMixin:
    """Look up a WikiPage by tag/slug path from the URL.

    Sets ``self.current_tag`` for use in context.
    Subclasses can set ``prefetch_page_tags = True`` to prefetch tags.
    """

    prefetch_page_tags = False

    def get_object(self, queryset=None):
        path = self.kwargs.get("path", "")
        tag, slug = parse_wiki_path(path)

        qs = WikiPageTag.objects.select_related("page")
        if self.prefetch_page_tags:
            qs = qs.prefetch_related("page__tags")

        try:
            page_tag = qs.get(tag=tag, slug=slug)
        except WikiPageTag.DoesNotExist:
            raise Http404(f"No wiki page found at '{path}'") from None

        self.current_tag = tag
        return page_tag.page

    def get_detail_path(self) -> str:
        """Build the URL path segment for this page's current tag location."""
        page: WikiPage = self.object  # type: ignore[attr-defined]
        if self.current_tag:
            return f"{self.current_tag}/{page.slug}"
        return page.slug


class WikiPageDetailView(WikiPagePathMixin, CanAccessMaintainerPortalMixin, DetailView):
    """Display a single wiki page."""

    model = WikiPage
    template_name = "wiki/page_detail.html"
    context_object_name = "page"
    prefetch_page_tags = True

    def post(self, request, *args, **kwargs):
        """Handle AJAX checkbox toggle updates."""
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "update_text":
            raw_text = request.POST.get("text", "")
            # Validate template marker syntax before saving
            template_errors = validate_template_syntax(raw_text)
            if template_errors:
                return JsonResponse({"success": False, "errors": template_errors}, status=400)
            self.object.updated_by = request.user
            try:
                save_inline_markdown_field(
                    self.object, "content", raw_text, extra_update_fields=["updated_by"]
                )
            except ValidationError as e:
                return JsonResponse({"success": False, "errors": e.messages}, status=400)
            # Sync template option index (page reloads on success, picks up toast)
            result = sync_template_option_index(self.object)
            _add_template_sync_toast(request, result)
            return JsonResponse({"success": True})

        return JsonResponse({"error": "Unknown action"}, status=400)

    def get_context_data(self, **kwargs):
        """Add wiki-specific context."""
        context = super().get_context_data(**kwargs)
        context["current_tag"] = self.current_tag
        context["nav_tree"] = build_nav_tree()
        context["detail_path"] = self.get_detail_path()
        # Filter in Python to use the prefetched page__tags cache
        context["other_tags"] = [t for t in self.object.tags.all() if t.tag != self.current_tag]
        return context


class WikiHomeView(CanAccessMaintainerPortalMixin, TemplateView):
    """Wiki home/index page."""

    template_name = "wiki/home.html"

    def get_context_data(self, **kwargs):
        """Add navigation tree to context."""
        context = super().get_context_data(**kwargs)
        context["nav_tree"] = build_nav_tree()
        # Show recent pages on home
        context["recent_pages"] = (
            WikiPage.objects.select_related("created_by", "updated_by")
            .prefetch_related("tags")
            .order_by("-updated_at")[:10]
        )
        return context


class WikiSearchView(CanAccessMaintainerPortalMixin, ListView):
    """Search wiki pages."""

    model = WikiPage
    template_name = "wiki/search.html"
    context_object_name = "pages"
    paginate_by = 20

    def get_queryset(self):
        """Filter pages by search query."""
        query = self.request.GET.get("q", "").strip()
        self.search_query = query

        return (
            WikiPage.objects.search(query)
            .select_related("created_by", "updated_by")
            .prefetch_related("tags")
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        """Add search query and nav tree to context."""
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.search_query
        context["nav_tree"] = build_nav_tree()
        return context


class WikiPageSuccessUrlMixin:
    """Shared success-URL logic for wiki create/edit views."""

    def get_success_url(self):
        """Redirect to the page detail view."""
        page = self.object
        first_tag = page.tags.first()
        if first_tag and first_tag.tag:
            path = f"{first_tag.tag}/{page.slug}"
        else:
            path = page.slug
        return reverse("wiki-page-detail", args=[path])


class WikiPageCreateView(
    WikiPageSuccessUrlMixin, FormPrefillMixin, CanAccessMaintainerPortalMixin, CreateView
):
    """Create a new wiki page."""

    model = WikiPage
    form_class = WikiPageForm
    template_name = "wiki/page_form.html"

    def get_initial(self):
        """Pre-fill content (via mixin) and title from session."""
        initial = super().get_initial()
        title = self.request.session.pop("form_prefill_title", None)
        if title:
            initial["title"] = title
        return initial

    def get_form_kwargs(self):
        """Pass tags from POST data or session prefill to form."""
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            kwargs["tags"] = self.request.POST.getlist("tags")
        else:
            tags = self.request.session.pop("form_prefill_tags", None)
            if tags:
                kwargs["tags"] = tags
        return kwargs

    def form_valid(self, form):
        """Set created_by and updated_by before saving."""
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        _add_template_sync_toast(self.request, form.template_sync_result)
        return response

    def get_context_data(self, **kwargs):
        """Add nav tree and page title."""
        context = super().get_context_data(**kwargs)
        context["nav_tree"] = build_nav_tree()
        context["page_title"] = "Create Wiki Page"
        context["is_create"] = True
        return context


class WikiPageEditView(
    WikiPageSuccessUrlMixin, WikiPagePathMixin, CanAccessMaintainerPortalMixin, UpdateView
):
    """Edit an existing wiki page."""

    model = WikiPage
    form_class = WikiPageForm
    template_name = "wiki/page_form.html"
    context_object_name = "page"

    def get_form_kwargs(self):
        """Pass tags from POST data to form."""
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            kwargs["tags"] = self.request.POST.getlist("tags")
        return kwargs

    def form_valid(self, form):
        """Set updated_by before saving."""
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        _add_template_sync_toast(self.request, form.template_sync_result)
        return response

    def get_context_data(self, **kwargs):
        """Add nav tree and page title."""
        context = super().get_context_data(**kwargs)
        context["nav_tree"] = build_nav_tree()
        context["page_title"] = f"Edit: {self.object.title}"
        context["is_create"] = False
        context["current_tag"] = self.current_tag
        context["detail_path"] = self.get_detail_path()
        return context


class WikiPageDeleteView(WikiPagePathMixin, CanAccessMaintainerPortalMixin, DeleteView):
    """Delete a wiki page."""

    model = WikiPage
    template_name = "wiki/page_confirm_delete.html"
    context_object_name = "page"

    def get_success_url(self):
        """Redirect to wiki home after deletion."""
        return reverse("wiki-home")

    def get_context_data(self, **kwargs):
        """Add nav tree and linking page warnings."""
        from .links import get_pages_linking_here

        context = super().get_context_data(**kwargs)
        context["nav_tree"] = build_nav_tree()
        context["current_tag"] = self.current_tag
        context["detail_path"] = self.get_detail_path()

        # Warn about pages that will have broken links
        context["linking_pages"] = get_pages_linking_here(self.object)

        return context


class WikiTagAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for wiki tag autocomplete."""

    def get(self, request, *args, **kwargs):
        """Return list of unique tags from WikiPageTag."""
        # Get all unique non-empty tags
        tags = (
            WikiPageTag.objects.exclude(tag=UNTAGGED_SENTINEL)
            .values_list("tag", flat=True)
            .distinct()
            .order_by("tag")
        )

        return JsonResponse({"tags": list(tags)})


def _resolve_template_tags(raw_tags: str, source_page: WikiPage) -> list[str]:
    """Resolve template tags, expanding ``@source`` to the source page's tags.

    Args:
        raw_tags: Comma-separated tag values, possibly including ``@source``.
        source_page: The wiki page containing the template.

    Returns:
        Deduplicated list of tag strings, preserving insertion order.
    """
    parts = [t.strip() for t in raw_tags.split(",") if t.strip()]
    result: list[str] = []
    source_tags: list[str] | None = None  # lazy-loaded, at most once
    for part in parts:
        if part == "@source":
            if source_tags is None:
                source_tags = list(
                    source_page.tags.exclude(tag=UNTAGGED_SENTINEL).values_list("tag", flat=True)
                )
            result.extend(source_tags)
        else:
            result.append(part)
    return list(dict.fromkeys(result))


class WikiTemplatePrefillView(CanAccessMaintainerPortalMixin, View):
    """Extract wiki template block content and redirect to a pre-filled create form."""

    def get(self, request, page_pk, template_name):
        page = get_object_or_404(WikiPage, pk=page_pk)
        action = extract_template_content(page.content, template_name)
        if action is None:
            raise Http404(f"Template block '{template_name}' not found")

        from the_flip.apps.core.markdown_links import convert_storage_to_authoring

        content = convert_storage_to_authoring(action.content)

        prefill_data = {
            "field": get_prefill_field(action.record_type),
            "content": content,
            "template_content_url": reverse(
                "api-wiki-template-content",
                kwargs={"page_pk": page_pk, "template_name": template_name},
            ),
        }

        extra_initial = {}
        if action.priority:
            extra_initial["priority"] = action.priority
        if extra_initial:
            prefill_data["extra_initial"] = extra_initial

        request.session["form_prefill"] = prefill_data

        if action.record_type == "page":
            if action.tags:
                tags = _resolve_template_tags(action.tags, page)
                if tags:
                    request.session["form_prefill_tags"] = tags
            if action.title:
                request.session["form_prefill_title"] = action.title

        return redirect(build_create_url(action))


class WikiReorderView(CanAccessMaintainerPortalMixin, TemplateView):
    """Dedicated page for reordering wiki docs and tags via drag-and-drop."""

    template_name = "wiki/reorder.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["nav_tree"] = build_nav_tree()
        return context


class WikiReorderSaveView(CanAccessMaintainerPortalMixin, View):
    """API endpoint to save wiki doc/tag reorder."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        page_orders = data.get("pages", [])
        tag_orders = data.get("tags", [])

        try:
            with transaction.atomic():
                for item in page_orders:
                    WikiPageTag.objects.filter(tag=item["tag"], slug=item["slug"]).update(
                        order=item["order"]
                    )

                for item in tag_orders:
                    WikiTagOrder.objects.update_or_create(
                        tag=item["tag"],
                        defaults={"order": item["order"]},
                    )
        except (KeyError, TypeError, ValueError) as e:
            return JsonResponse({"error": f"Invalid payload: {e}"}, status=400)

        return JsonResponse({"status": "success"})


class WikiTemplateListView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint listing template options matching filters.

    Query parameters:
        record_type (required): problem, log, partrequest, page
        priority: filter by priority (blank matches all)
        machine_slug: filter by machine slug (blank matches all)
        location_slug: filter by location slug (blank matches all)
    """

    def get(self, request, *args, **kwargs):
        record_type = request.GET.get("record_type", "")
        if not record_type:
            return JsonResponse({"error": "record_type is required"}, status=400)

        qs = TemplateOptionIndex.objects.filter(record_type=record_type).select_related("page")

        priority = request.GET.get("priority", "")
        if priority:
            qs = qs.filter(Q(priority=priority) | Q(priority=""))
        # No priority filter means show only templates that work for any priority

        machine_slug = request.GET.get("machine_slug", "")
        if machine_slug:
            qs = qs.filter(Q(machine_slug=machine_slug) | Q(machine_slug=""))
        else:
            qs = qs.filter(machine_slug="")

        location_slug = request.GET.get("location_slug", "")
        if location_slug:
            qs = qs.filter(Q(location_slug=location_slug) | Q(location_slug=""))
        else:
            qs = qs.filter(location_slug="")

        templates = [
            {
                "label": t.label,
                "page_title": t.page.title,
                "content_url": reverse(
                    "api-wiki-template-content",
                    kwargs={"page_pk": t.page_id, "template_name": t.template_name},
                ),
            }
            for t in qs
        ]

        return JsonResponse({"templates": templates})


class WikiTemplateContentView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint returning the content of a single template block."""

    def get(self, request, page_pk, template_name):
        page = get_object_or_404(WikiPage, pk=page_pk)
        action = extract_template_content(page.content, template_name)
        if action is None:
            raise Http404(f"Template block '{template_name}' not found")

        from the_flip.apps.core.markdown_links import convert_storage_to_authoring

        data: dict[str, str | list[str]] = {
            "content": convert_storage_to_authoring(action.content),
        }

        if action.record_type == "page":
            if action.tags:
                data["tags"] = _resolve_template_tags(action.tags, page)
            if action.title:
                data["title"] = action.title

        if action.priority:
            data["priority"] = action.priority

        return JsonResponse(data)
