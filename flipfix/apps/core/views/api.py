"""Read-only API endpoints for internal service consumers."""

from __future__ import annotations

from django.http import Http404, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.api_auth import json_api_view, validate_api_key


def _serialize_machine(m: MachineInstance) -> dict:
    """Serialize a MachineInstance to a dict for JSON responses."""
    return {
        "asset_id": m.asset_id,
        "name": m.name,
        "short_name": m.short_name,
        "slug": m.slug,
        "serial_number": m.serial_number,
        "operational_status": m.operational_status,
        "location": m.location.name if m.location else None,
        "model": {
            "name": m.model.name,
            "manufacturer": m.model.manufacturer,
            "year": m.model.year,
        },
    }


@method_decorator(csrf_exempt, name="dispatch")
class MachineListApiView(View):
    """Read-only API: list all machines with model and location info."""

    @json_api_view
    def get(self, request):
        validate_api_key(request)

        machines = MachineInstance.objects.select_related("model", "location").order_by(
            "model__sort_name"
        )

        return JsonResponse({"machines": [_serialize_machine(m) for m in machines]})


@method_decorator(csrf_exempt, name="dispatch")
class MachineDetailApiView(View):
    """Read-only API: get a single machine by asset ID."""

    @json_api_view
    def get(self, request, asset_id: str):
        validate_api_key(request)

        try:
            machine = MachineInstance.objects.select_related("model", "location").get(
                asset_id=asset_id.upper()
            )
        except MachineInstance.DoesNotExist as e:
            raise Http404(f"Machine with asset ID '{asset_id}' not found") from e

        return JsonResponse({"machine": _serialize_machine(machine)})
