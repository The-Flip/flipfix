from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.maintenance.models import LogEntry


class MachineInlineUpdateView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX-only endpoint to update machine status/location."""

    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, *args, **kwargs):
        machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        action = request.POST.get("action")

        if action == "update_status":
            status = request.POST.get("operational_status")
            if status in dict(MachineInstance.STATUS_CHOICES):
                if machine.operational_status == status:
                    return JsonResponse({"status": "noop"})
                machine.operational_status = status
                machine.updated_by = request.user
                machine.save(update_fields=["operational_status", "updated_by", "updated_at"])
                log_entry_html = self._render_latest_log_entry(machine)
                return JsonResponse(
                    {
                        "status": "success",
                        "operational_status": status,
                        "operational_status_display": machine.get_operational_status_display(),
                        "log_entry_html": log_entry_html,
                    }
                )
            return JsonResponse({"error": "Invalid status"}, status=400)

        if action == "update_location":
            location_slug = request.POST.get("location")
            if not location_slug:
                if machine.location is None:
                    return JsonResponse({"status": "noop"})
                machine.location = None
                machine.updated_by = request.user
                machine.save(update_fields=["location", "updated_by", "updated_at"])
                log_entry_html = self._render_latest_log_entry(machine)
                return JsonResponse(
                    {
                        "status": "success",
                        "location": "",
                        "location_display": "",
                        "log_entry_html": log_entry_html,
                    }
                )
            try:
                location = Location.objects.get(slug=location_slug)
                if machine.location and machine.location.slug == location.slug:
                    return JsonResponse({"status": "noop"})
                machine.location = location
                machine.updated_by = request.user
                machine.save(update_fields=["location", "updated_by", "updated_at"])
                celebration = location.slug == "floor"
                log_entry_html = self._render_latest_log_entry(machine)
                return JsonResponse(
                    {
                        "status": "success",
                        "location": location.slug,
                        "location_display": location.name,
                        "celebration": celebration,
                        "log_entry_html": log_entry_html,
                    }
                )
            except Location.DoesNotExist:
                return JsonResponse({"error": "Invalid location"}, status=400)

        return JsonResponse({"error": "Unknown action"}, status=400)

    def _render_latest_log_entry(self, machine):
        """Render the most recent log entry as HTML for injection into the feed."""
        log_entry = LogEntry.objects.filter(machine=machine).order_by("-created_at").first()
        if not log_entry:
            return ""
        return render_to_string(
            "maintenance/partials/log_entry.html",
            {"entry": log_entry},
        )
