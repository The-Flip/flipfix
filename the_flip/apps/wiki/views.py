"""Wiki views."""

from __future__ import annotations

import json

from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin

from .actions import build_create_url, extract_action_content, get_prefill_field
from .forms import WikiPageForm
from .models import UNTAGGED_SENTINEL, WikiPage, WikiPageTag, WikiTagOrder


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
            WikiPage.objects.select_related("created_by", "modified_by")
            .prefetch_related("tags")
            .order_by("-modified_at")[:10]
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

        if not query:
            return WikiPage.objects.none()

        return (
            WikiPage.objects.filter(
                Q(title__icontains=query)
                | Q(slug__icontains=query)
                | Q(content__icontains=query)
                | Q(tags__tag__icontains=query)
            )
            .distinct()
            .select_related("created_by", "modified_by")
            .prefetch_related("tags")
            .order_by("-modified_at")
        )

    def get_context_data(self, **kwargs):
        """Add search query and nav tree to context."""
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.search_query
        context["nav_tree"] = build_nav_tree()
        return context


def build_nav_tree() -> dict:
    """Build the navigation tree from WikiPageTag records.

    Returns a nested dict structure representing the tag hierarchy with pages.

    Structure:
        {
            'pages': [...],  # Untagged pages (tag='')
            'children': {
                'machines': {
                    'pages': [...],  # Pages directly in 'machines'
                    'children': {
                        'blackout': {
                            'pages': [...],  # Pages in 'machines/blackout'
                            'children': {...}
                        }
                    }
                }
            }
        }
    """
    from .models import WikiTagOrder

    # Query 1: All page-tag relationships with page data
    page_tags = WikiPageTag.objects.select_related("page").all()

    # Query 2: Tag ordering
    tag_orders = {o.tag: o.order for o in WikiTagOrder.objects.all()}

    # Build tree structure
    tree: dict = {"pages": [], "children": {}}

    for pt in page_tags:
        if not pt.tag:
            # Untagged page - goes at root level
            tree["pages"].append(
                {
                    "page": pt.page,
                    "order": pt.order,
                    "path": pt.slug,
                }
            )
        else:
            # Navigate/create path through tree
            segments = pt.tag.split("/")
            node = tree
            current_path = ""

            for segment in segments:
                current_path = f"{current_path}/{segment}" if current_path else segment
                if segment not in node["children"]:
                    node["children"][segment] = {
                        "pages": [],
                        "children": {},
                        "tag_path": current_path,
                        "order": tag_orders.get(current_path),
                    }
                node = node["children"][segment]

            # Add page to the final node
            node["pages"].append(
                {
                    "page": pt.page,
                    "order": pt.order,
                    "path": f"{pt.tag}/{pt.slug}",
                }
            )

    _sort_nav_tree(tree)

    return tree


def _sort_nav_tree(node: dict) -> None:
    """Sort pages and children within each nav tree node recursively.

    Ordered items sort first (by order value), then alphabetically.
    """
    node["pages"] = sorted(
        node["pages"],
        key=lambda p: (p["order"] is None, p["order"] or 0, p["page"].title.lower()),
    )
    node["children"] = dict(
        sorted(
            node["children"].items(),
            key=lambda item: (
                item[1]["order"] is None,
                item[1]["order"] or 0,
                item[0].lower(),
            ),
        )
    )
    for child in node["children"].values():
        _sort_nav_tree(child)


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


class WikiPageCreateView(WikiPageSuccessUrlMixin, CanAccessMaintainerPortalMixin, CreateView):
    """Create a new wiki page."""

    model = WikiPage
    form_class = WikiPageForm
    template_name = "wiki/page_form.html"

    def get_form_kwargs(self):
        """Pass tags from POST data to form."""
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            kwargs["tags"] = self.request.POST.getlist("tags")
        return kwargs

    def form_valid(self, form):
        """Set created_by and modified_by before saving."""
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        return super().form_valid(form)

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
        """Set modified_by before saving."""
        form.instance.modified_by = self.request.user
        return super().form_valid(form)

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


class WikiActionPrefillView(CanAccessMaintainerPortalMixin, View):
    """Extract wiki action block content and redirect to a pre-filled create form."""

    def get(self, request, page_pk, action_name):
        page = get_object_or_404(WikiPage, pk=page_pk)
        action = extract_action_content(page.content, action_name)
        if action is None:
            raise Http404(f"Action block '{action_name}' not found")

        from the_flip.apps.core.markdown_links import convert_storage_to_authoring

        content = convert_storage_to_authoring(action.content)

        request.session["form_prefill"] = {
            "field": get_prefill_field(action.record_type),
            "content": content,
        }
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
        except (KeyError, TypeError) as e:
            return JsonResponse({"error": f"Invalid payload: {e}"}, status=400)

        return JsonResponse({"status": "success"})
