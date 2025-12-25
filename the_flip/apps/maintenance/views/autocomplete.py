"""AJAX autocomplete endpoints for maintainer portal."""

from __future__ import annotations

from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Max,
    Q,
    Value,
    When,
)
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.views import View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin
from the_flip.apps.maintenance.models import ProblemReport


class MaintainerAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for maintainer name autocomplete."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip().lower()
        maintainers = Maintainer.objects.filter(is_shared_account=False).select_related("user")

        results = []
        for m in maintainers:
            display_name = m.display_name
            username = m.user.username
            first_name = (m.user.first_name or "").lower()
            last_name = (m.user.last_name or "").lower()
            if query and not (
                first_name.startswith(query)
                or last_name.startswith(query)
                or username.lower().startswith(query)
            ):
                continue
            results.append(
                {
                    "id": m.id,
                    "display_name": display_name,
                    "username": username,
                    "first_name": m.user.first_name or "",
                    "last_name": m.user.last_name or "",
                }
            )

        # Sort alphabetically by display name
        results.sort(key=lambda x: x["display_name"].lower())
        return JsonResponse({"maintainers": results})


class MachineAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for machine autocomplete (maintainer-only)."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        machines = (
            MachineInstance.objects.select_related("model", "location")
            .annotate(
                open_report_count=Count(
                    "problem_reports", filter=Q(problem_reports__status=ProblemReport.Status.OPEN)
                ),
                latest_open_report_date=Max(
                    "problem_reports__created_at",
                    filter=Q(problem_reports__status=ProblemReport.Status.OPEN),
                ),
            )
            .order_by(
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
                    output_field=IntegerField(),
                ),
                F("latest_open_report_date").desc(nulls_last=True),
                Lower("model__name"),
            )
        )

        if query:
            machines = machines.filter(
                Q(name__icontains=query)
                | Q(model__name__icontains=query)
                | Q(location__name__icontains=query)
                | Q(slug__icontains=query)
            )

        machines = machines[:50]

        results = []
        for machine in machines:
            results.append(
                {
                    "id": machine.id,
                    "slug": machine.slug,
                    "name": machine.name,
                    "location": machine.location.name if machine.location else "",
                }
            )

        return JsonResponse({"machines": results})


class ProblemReportAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for problem report autocomplete (maintainer-only).

    Returns open problem reports grouped by machine, with current machine first.
    Includes a "None" option for unlinking log entries.
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        query = request.GET.get("q", "").strip()
        current_machine_slug = request.GET.get("current_machine", "")

        reports = (
            ProblemReport.objects.filter(status=ProblemReport.Status.OPEN)
            .select_related("machine", "machine__model", "machine__location")
            .order_by("-created_at")
        )

        if query:
            reports = reports.filter(
                Q(description__icontains=query)
                | Q(machine__model__name__icontains=query)
                | Q(machine__name__icontains=query)
            )

        reports = reports[:100]

        # Group reports by machine
        grouped: dict[str, list[dict]] = {}
        current_machine_reports: list[dict] = []

        for report in reports:
            machine = report.machine
            report_data = {
                "id": report.id,
                "machine_slug": machine.slug,
                "machine_name": machine.name,
                "summary": self._get_summary(report),
                "created_at": report.created_at.isoformat(),
            }

            if machine.slug == current_machine_slug:
                current_machine_reports.append(report_data)
            else:
                machine_key = machine.name
                if machine_key not in grouped:
                    grouped[machine_key] = []
                grouped[machine_key].append(report_data)

        # Build result with current machine first
        result_groups = []
        if current_machine_reports:
            # Get machine name from first report
            machine_name = current_machine_reports[0]["machine_name"]
            result_groups.append(
                {"machine_name": f"{machine_name} (current)", "reports": current_machine_reports}
            )

        # Add other machines sorted alphabetically
        for machine_name in sorted(grouped.keys()):
            result_groups.append({"machine_name": machine_name, "reports": grouped[machine_name]})

        return JsonResponse({"groups": result_groups})

    def _get_summary(self, report: ProblemReport) -> str:
        """Build a concise problem report summary for the dropdown."""
        if report.problem_type == ProblemReport.ProblemType.OTHER:
            if report.description:
                desc = report.description[:60]
                if len(report.description) > 60:
                    desc += "..."
                return desc
            return "No description"
        else:
            type_label = report.get_problem_type_display()
            if report.description:
                desc = report.description[:40]
                if len(report.description) > 40:
                    desc += "..."
                return f"{type_label}: {desc}"
            return type_label
