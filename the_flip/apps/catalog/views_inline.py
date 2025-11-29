from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from the_flip.apps.catalog.models import Location, MachineInstance


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
                return JsonResponse(
                    {
                        "status": "success",
                        "operational_status": status,
                        "operational_status_display": machine.get_operational_status_display(),
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
                return JsonResponse({"status": "success", "location": "", "location_display": ""})
            try:
                location = Location.objects.get(slug=location_slug)
                if machine.location and machine.location.slug == location.slug:
                    return JsonResponse({"status": "noop"})
                machine.location = location
                machine.updated_by = request.user
                machine.save(update_fields=["location", "updated_by", "updated_at"])
                return JsonResponse(
                    {
                        "status": "success",
                        "location": location.slug,
                        "location_display": location.name,
                    }
                )
            except Location.DoesNotExist:
                return JsonResponse({"error": "Invalid location"}, status=400)

        return JsonResponse({"error": "Unknown action"}, status=400)
