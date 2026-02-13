from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin
from the_flip.apps.maintenance.models import LogEntry


class MachineInlineUpdateView(CanAccessMaintainerPortalMixin, View):
    """AJAX-only endpoint to update machine status/location."""

    def post(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        action = request.POST.get("action")

        action_handlers = {
            "update_status": self._handle_update_status,
            "update_location": self._handle_update_location,
        }

        if action in action_handlers:
            return action_handlers[action](request)

        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)

    # -- Action handlers -------------------------------------------------------

    def _handle_update_status(self, request):
        """AJAX: change operational status."""
        status = request.POST.get("operational_status")
        if status not in MachineInstance.OperationalStatus.values:
            return JsonResponse({"success": False, "error": "Invalid status"}, status=400)

        if self.machine.operational_status == status:
            return JsonResponse({"success": True, "status": "noop"})

        self.machine.operational_status = status
        self.machine.updated_by = request.user
        self.machine.save(update_fields=["operational_status", "updated_by", "updated_at"])
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "operational_status": status,
                "operational_status_display": self.machine.get_operational_status_display(),
                "log_entry_html": self._render_latest_log_entry(self.machine),
                "entry_type": "log",
            }
        )

    def _handle_update_location(self, request):
        """AJAX: change machine location."""
        location_slug = request.POST.get("location")

        if not location_slug:
            if self.machine.location is None:
                return JsonResponse({"success": True, "status": "noop"})
            self.machine.location = None
            self.machine.updated_by = request.user
            self.machine.save(update_fields=["location", "updated_by", "updated_at"])
            return JsonResponse(
                {
                    "success": True,
                    "status": "success",
                    "location": "",
                    "location_display": "",
                    "log_entry_html": self._render_latest_log_entry(self.machine),
                    "entry_type": "log",
                }
            )

        try:
            location = Location.objects.get(slug=location_slug)
        except Location.DoesNotExist:
            return JsonResponse({"success": False, "error": "Invalid location"}, status=400)

        if self.machine.location and self.machine.location.slug == location.slug:
            return JsonResponse({"success": True, "status": "noop"})

        self.machine.location = location
        self.machine.updated_by = request.user
        self.machine.save(update_fields=["location", "updated_by", "updated_at"])
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "location": location.slug,
                "location_display": location.name,
                "celebration": location.slug == "floor",
                "log_entry_html": self._render_latest_log_entry(self.machine),
                "entry_type": "log",
            }
        )

    def _render_latest_log_entry(self, machine):
        """Render the most recent log entry as HTML for injection into the feed."""
        log_entry = (
            LogEntry.objects.filter(machine=machine)
            .select_related("problem_report")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
            .first()
        )
        if not log_entry:
            return ""
        return render_to_string(
            "maintenance/partials/log_entry.html",
            {"entry": log_entry},
        )
