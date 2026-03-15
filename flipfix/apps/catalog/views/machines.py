from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Case, CharField, Count, F, Max, Prefetch, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView, UpdateView

from flipfix.apps.catalog.forms import (
    MachineCommentForm,
    MachineCreateModelDoesNotExistForm,
    MachineCreateModelExistsForm,
    MachineInstanceForm,
    MachineModelForm,
)
from flipfix.apps.catalog.models import Location, MachineInstance, MachineModel
from flipfix.apps.core.feed import FEED_CONFIGS, PageCursor, get_feed_page
from flipfix.apps.core.forms import SearchForm
from flipfix.apps.core.url_utils import build_filter_url
from flipfix.apps.maintenance.models import ProblemReport

VALID_MACHINE_STATUSES = {s.value for s in MachineInstance.OperationalStatus}


class MachineListView(ListView):
    """Maintainer machine list with status/location filter stats in the sidebar."""

    template_name = "catalog/machine_list_for_maintainers.html"
    context_object_name = "machines"

    def get_queryset(self):
        qs = (
            MachineInstance.objects.visible()
            .annotate(
                # Count open problem reports
                open_report_count=Count(
                    "problem_reports", filter=Q(problem_reports__status=ProblemReport.Status.OPEN)
                ),
                # Get the most recent open problem report date
                latest_open_report_date=Max(
                    "problem_reports__occurred_at",
                    filter=Q(problem_reports__status=ProblemReport.Status.OPEN),
                ),
            )
            .prefetch_related(
                Prefetch(
                    "problem_reports",
                    queryset=ProblemReport.objects.filter(
                        status=ProblemReport.Status.OPEN
                    ).order_by("-occurred_at")[:1],
                    to_attr="latest_open_report",
                )
            )
            .order_by(
                # 1. Status priority: fixing, broken, unknown, good
                Case(
                    When(
                        operational_status=MachineInstance.OperationalStatus.FIXING, then=Value(1)
                    ),
                    When(
                        operational_status=MachineInstance.OperationalStatus.BROKEN, then=Value(2)
                    ),
                    When(
                        operational_status=MachineInstance.OperationalStatus.UNKNOWN, then=Value(3)
                    ),
                    When(operational_status=MachineInstance.OperationalStatus.GOOD, then=Value(4)),
                    default=Value(5),
                    output_field=CharField(),
                ),
                # 2. Machines with open problem reports first
                F("latest_open_report_date").desc(nulls_last=True),
                # 3. Machine name as tie-breaker
                Lower("model__sort_name"),
            )
        )

        # Apply query param filters
        status_filter = self.request.GET.get("status", "")
        if status_filter in VALID_MACHINE_STATUSES:
            qs = qs.filter(operational_status=status_filter)

        location_filter = self.request.GET.get("location", "")
        if location_filter and Location.objects.filter(slug=location_filter).exists():
            qs = qs.filter(location__slug=location_filter)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        path = self.request.path
        params = self.request.GET

        status_filter = params.get("status", "")
        location_filter = params.get("location", "")

        # Use conditional aggregation for status counts (single query)
        status_counts = MachineInstance.objects.visible().aggregate(
            total=Count("id"),
            good=Count("id", filter=Q(operational_status="good")),
            fixing=Count("id", filter=Q(operational_status="fixing")),
            broken=Count("id", filter=Q(operational_status="broken")),
        )

        # Status stats
        status_stats = [
            {
                "value": status_counts["total"],
                "label": "All",
                "url": build_filter_url(path, params, status=None),
                "active": not status_filter,
            },
            {
                "value": status_counts["fixing"],
                "label": "Fixing",
                "url": build_filter_url(path, params, status="fixing"),
                "active": status_filter == "fixing",
                "variant": "status-fixing",
            },
            {
                "value": status_counts["broken"],
                "label": "Broken",
                "url": build_filter_url(path, params, status="broken"),
                "active": status_filter == "broken",
                "variant": "status-broken",
            },
            {
                "value": status_counts["good"],
                "label": "Good",
                "url": build_filter_url(path, params, status="good"),
                "active": status_filter == "good",
                "variant": "status-good",
            },
        ]

        # Location stats from unfiltered queryset (single query with conditional aggregation)
        locations = Location.objects.all()
        location_agg = {f"loc_{loc.slug}": Count("id", filter=Q(location=loc)) for loc in locations}
        location_counts = MachineInstance.objects.visible().aggregate(
            total=Count("id"), **location_agg
        )

        location_stats = [
            {
                "value": location_counts["total"],
                "label": "All",
                "url": build_filter_url(path, params, location=None),
                "active": not location_filter,
            },
        ]
        for loc in locations:
            count = location_counts[f"loc_{loc.slug}"]
            if count > 0:
                location_stats.append(
                    {
                        "value": count,
                        "label": loc.name,
                        "url": build_filter_url(path, params, location=loc.slug),
                        "active": location_filter == loc.slug,
                    }
                )

        context["status_stats"] = status_stats
        context["location_stats"] = location_stats
        context["meta_description"] = (
            "Pinball machines at The Flip, Chicago's playable pinball museum"
            " — status, repairs, and logs."
        )

        return context


class MachineDetailViewForPublic(DetailView):
    """Public machine detail page with problem report form."""

    template_name = "catalog/machine_detail_public.html"
    queryset = MachineInstance.objects.visible()
    slug_field = "slug"
    slug_url_kwarg = "slug"


class MachineFeedView(TemplateView):
    """Feed of activity on a specific machine, with filtering and search."""

    template_name = "catalog/machine_feed.html"

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(
            MachineInstance.objects.select_related("model", "owner"), slug=kwargs["slug"]
        )
        # Figure out what types of feed items to show
        self.feed_filter_type = request.GET.get("f", "all")
        if self.feed_filter_type not in FEED_CONFIGS:
            self.feed_filter_type = "all"
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        feed_config = FEED_CONFIGS[self.feed_filter_type]
        search_query = self.request.GET.get("q", "").strip()

        # Get first page of entries
        entries, has_next = get_feed_page(
            machine=self.machine,
            entry_types=feed_config.entry_types,
            page_num=1,
            search_query=search_query or None,
        )

        context.update(
            {
                "machine": self.machine,
                "entries": entries,
                "page_obj": PageCursor(has_next=has_next, page_num=1),
                "active_filter": self.feed_filter_type,
                "search_form": SearchForm(initial={"q": search_query}),
                "locations": Location.objects.all(),
                # Feed config context
                "title_suffix": feed_config.title_suffix,
                "breadcrumb_label": feed_config.breadcrumb_label,
                "entry_types": feed_config.entry_types,
                "empty_message": feed_config.empty_message,
                "search_empty_message": feed_config.search_empty_message,
                "meta_description": (
                    f"{self.machine.name} at The Flip"
                    f" — {self.machine.get_operational_status_display().lower()}."
                ),
            }
        )
        return context


class MachineFeedPartialView(View):
    """AJAX endpoint for infinite scroll of machine feed entries."""

    def get(self, request, slug):
        try:
            machine = MachineInstance.objects.get(slug=slug)
        except MachineInstance.DoesNotExist:
            return JsonResponse({"error": "Machine not found"}, status=404)

        # Get feed filter param
        feed = request.GET.get("f", "all")
        if feed not in FEED_CONFIGS:
            feed = "all"
        feed_config = FEED_CONFIGS[feed]

        try:
            page_num = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            page_num = 1
        search_query = request.GET.get("q", "").strip() or None

        page_items, has_next = get_feed_page(
            machine=machine,
            entry_types=feed_config.entry_types,
            page_num=page_num,
            search_query=search_query,
        )

        # Render each entry using the activity_entry dispatcher template
        items_html = "".join(
            render_to_string(
                "maintenance/partials/activity_entry.html", {"entry": entry}, request=request
            )
            for entry in page_items
        )

        return JsonResponse(
            {
                "items": items_html,
                "has_next": has_next,
                "next_page": page_num + 1 if has_next else None,
            }
        )


class MachineDetailsView(DetailView):
    """Read-only machine info page with comments."""

    template_name = "catalog/machine_details.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "machine"

    def get_queryset(self):
        return MachineInstance.objects.select_related("model", "owner", "location")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["comments"] = self.object.comments.select_related("posted_by").all()
        context["comment_form"] = MachineCommentForm()
        return context

    def post(self, request, *args, **kwargs):
        """Handle comment creation."""
        self.object = self.get_object()
        action = request.POST.get("action", "")

        if action == "add_comment":
            form = MachineCommentForm(request.POST)
            if form.is_valid():
                comment = form.save(commit=False)
                comment.machine = self.object
                comment.posted_by = request.user
                comment.save()
                messages.success(request, "Comment added.")
            else:
                for error in form.errors.values():
                    messages.error(request, error[0])

        return redirect("machine-details", slug=self.object.slug)


class MachineUpdateView(UpdateView):
    """Edit machine instance details (excluding model)."""

    form_class = MachineInstanceForm
    template_name = "catalog/machine_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return MachineInstance.objects.select_related("model", "owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("maintainer-machine-detail", kwargs={"slug": self.object.slug})


class MachineModelUpdateView(SuccessMessageMixin, UpdateView):
    """Edit the pinball machine model."""

    model = MachineModel
    form_class = MachineModelForm
    template_name = "catalog/machine_model_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"
    success_message = "Model '%(name)s' saved."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all instances of this model for sidebar
        instances = self.object.instances.all()
        context["instances"] = instances
        # Get first instance for breadcrumb navigation
        context["machine_instance"] = instances.first() if instances else None
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("machine-model-edit", kwargs={"slug": self.object.slug})


class MachineCreateLandingView(View):
    """Landing page for adding a new machine - select model first."""

    template_name = "catalog/machine_create_landing.html"

    def get(self, request):
        context = {"models": MachineModel.objects.all().order_by("sort_name")}
        return TemplateResponse(request, self.template_name, context)

    def post(self, request):
        """Handle form submission - redirect to selected model page."""
        selected_slug = request.POST.get("model_slug", "")

        if selected_slug == "new":
            return redirect("machine-create-model-does-not-exist")

        # Validate the slug exists
        model = get_object_or_404(MachineModel, slug=selected_slug)
        return redirect("machine-create-model-exists", model_slug=model.slug)


class MachineCreateModelExistsView(FormView):
    """Add an instance of a specific machine model."""

    template_name = "catalog/machine_create_model_exists.html"
    form_class = MachineCreateModelExistsForm

    def dispatch(self, request, *args, **kwargs):
        self.machine_model = get_object_or_404(MachineModel, slug=kwargs["model_slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine_model"] = self.machine_model
        context["existing_instances"] = self.machine_model.instances.all()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["model_name"] = self.machine_model.name
        kwargs["instance_count"] = self.machine_model.instances.count()
        return kwargs

    def form_valid(self, form):
        instance = MachineInstance.objects.create(
            model=self.machine_model,
            name=form.cleaned_data["instance_name"],
            operational_status=MachineInstance.OperationalStatus.UNKNOWN,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        messages.success(
            self.request,
            format_html(
                'Machine created! You can now <a href="{}">edit the machine</a> or <a href="{}">edit the model</a>.',
                reverse("machine-edit", kwargs={"slug": instance.slug}),
                reverse("machine-model-edit", kwargs={"slug": self.machine_model.slug}),
            ),
        )
        return redirect("maintainer-machine-detail", slug=instance.slug)


class MachineCreateModelDoesNotExistView(FormView):
    """Create a new machine model and first instance."""

    template_name = "catalog/machine_create_model_does_not_exist.html"
    form_class = MachineCreateModelDoesNotExistForm

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        with transaction.atomic():
            model = MachineModel.objects.create(
                name=cleaned_data["name"],
                manufacturer=cleaned_data.get("manufacturer") or "",
                year=cleaned_data.get("year"),
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            instance = MachineInstance.objects.create(
                model=model,
                name=cleaned_data["name"],  # First instance uses model name
                operational_status=MachineInstance.OperationalStatus.UNKNOWN,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
        messages.success(
            self.request,
            format_html(
                'Machine created! You can now <a href="{}">edit the machine</a> and <a href="{}">edit the model</a>.',
                reverse("machine-edit", kwargs={"slug": instance.slug}),
                reverse("machine-model-edit", kwargs={"slug": model.slug}),
            ),
        )
        return redirect("maintainer-machine-detail", slug=instance.slug)
