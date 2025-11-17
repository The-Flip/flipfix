from django.db.models import Case, CharField, Count, Q, Value, When
from django.db.models.functions import Coalesce, Lower
from django.views.generic import DetailView, ListView

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import ProblemReportForm
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


class PublicMachineListView(ListView):
    template_name = "catalog/machine_list_public.html"
    context_object_name = "machines"

    def get_queryset(self):
        return MachineInstance.objects.visible().annotate(
            open_report_count=Count(
                'problem_reports',
                filter=Q(problem_reports__status=ProblemReport.STATUS_OPEN)
            )
        ).order_by(
            # Machines with open problem reports first
            '-open_report_count',
            # Location priority: workshop, storage, floor
            Case(
                When(location=MachineInstance.LOCATION_WORKSHOP, then=Value(1)),
                When(location=MachineInstance.LOCATION_STORAGE, then=Value(2)),
                When(location=MachineInstance.LOCATION_FLOOR, then=Value(3)),
                default=Value(4),
                output_field=CharField(),
            ),
            # Status priority: fixing, broken, good, unknown
            Case(
                When(operational_status=MachineInstance.STATUS_FIXING, then=Value(1)),
                When(operational_status=MachineInstance.STATUS_BROKEN, then=Value(2)),
                When(operational_status=MachineInstance.STATUS_GOOD, then=Value(3)),
                When(operational_status=MachineInstance.STATUS_UNKNOWN, then=Value(4)),
                default=Value(5),
                output_field=CharField(),
            ),
            # Alphabetically by display name (name_override if present, else model.name)
            Lower(Coalesce("name_override", "model__name")),
        )


class MachineListView(PublicMachineListView):
    template_name = "catalog/machine_list.html"


class PublicMachineDetailView(DetailView):
    template_name = "catalog/machine_detail.html"
    queryset = MachineInstance.objects.visible()
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object
        context["problem_reports"] = ProblemReport.objects.filter(machine=machine).select_related("reported_by_user")
        context["log_entries"] = (
            LogEntry.objects.filter(machine=machine)
            .select_related("problem_report")
            .prefetch_related("maintainers", "media")
        )
        context["problem_report_form"] = ProblemReportForm()
        return context


class MachineDetailView(PublicMachineDetailView):
    """Maintainer-facing detail page; customize as needed."""

    template_name = "catalog/maintainer_machine_detail.html"
