"""API endpoints for internal service consumers."""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.api_auth import json_api_view, validate_api_key
from flipfix.apps.maintenance.models import ProblemReport


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
            "month": m.model.month,
            "era": m.model.era,
            "system": m.model.system,
            "scoring": m.model.scoring,
            "flipper_count": m.model.flipper_count,
            "ipdb_id": m.model.ipdb_id,
            "pinside_rating": (
                float(m.model.pinside_rating) if m.model.pinside_rating is not None else None
            ),
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


def _serialize_problem_report(report: ProblemReport) -> dict:
    """Serialize a ProblemReport to a dict for JSON responses."""
    return {
        "id": report.pk,
        "machine_asset_id": report.machine.asset_id,
        "status": report.status,
        "priority": report.priority,
        "problem_type": report.problem_type,
        "description": report.description,
        "reported_by_name": report.reported_by_name,
        "occurred_at": report.occurred_at.isoformat(),
        "created_at": report.created_at.isoformat(),
    }


@method_decorator(csrf_exempt, name="dispatch")
class MachineProblemReportCreateApiView(View):
    """Write API: file a problem report against a machine.

    Requires an API key with ``can_write`` enabled.  Optionally marks the
    machine ``broken`` in the same transaction (``mark_broken``).  Filing a
    second open ``unplayable`` report for a machine is idempotent: the
    existing open report is returned rather than a duplicate created.
    """

    @json_api_view
    def post(self, request, asset_id: str):
        validate_api_key(request, require_write=True)

        try:
            machine = MachineInstance.objects.get(asset_id=asset_id.upper())
        except MachineInstance.DoesNotExist as e:
            raise Http404(f"Machine with asset ID '{asset_id}' not found") from e

        payload = self._parse_payload(request)

        # Idempotency: juice may re-detect the same fault.  Return the existing
        # open unplayable report instead of creating a duplicate.
        if payload["priority"] == ProblemReport.Priority.UNPLAYABLE:
            existing = (
                ProblemReport.objects.filter(
                    machine=machine,
                    status=ProblemReport.Status.OPEN,
                    priority=ProblemReport.Priority.UNPLAYABLE,
                )
                .order_by("-occurred_at")
                .first()
            )
            if existing is not None:
                return JsonResponse(
                    {"problem_report": _serialize_problem_report(existing)}, status=200
                )

        with transaction.atomic():
            report = ProblemReport.objects.create(
                machine=machine,
                priority=payload["priority"],
                problem_type=payload["problem_type"],
                description=payload["description"],
                reported_by_name=payload["reported_by_name"],
                occurred_at=payload["occurred_at"],
            )
            if payload["mark_broken"] and (
                machine.operational_status != MachineInstance.OperationalStatus.BROKEN
            ):
                machine.operational_status = MachineInstance.OperationalStatus.BROKEN
                machine.save(update_fields=["operational_status", "updated_at"])

        return JsonResponse({"problem_report": _serialize_problem_report(report)}, status=201)

    @staticmethod
    def _parse_payload(request) -> dict:
        """Validate and normalize the JSON request body.

        Raises ``ValidationError`` (rendered as 400) on malformed input.
        """
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError as e:
            raise ValidationError("Request body must be valid JSON") from e
        if not isinstance(body, dict):
            raise ValidationError("Request body must be a JSON object")

        priority = body.get("priority", ProblemReport.Priority.MINOR)
        if priority not in ProblemReport.Priority.values:
            raise ValidationError(f"Invalid priority: {priority!r}")

        problem_type = body.get("problem_type", ProblemReport.ProblemType.OTHER)
        if problem_type not in ProblemReport.ProblemType.values:
            raise ValidationError(f"Invalid problem_type: {problem_type!r}")

        occurred_at_raw = body.get("occurred_at")
        if occurred_at_raw:
            occurred_at = parse_datetime(occurred_at_raw)
            if occurred_at is None:
                raise ValidationError("Invalid occurred_at: expected an ISO-8601 datetime")
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
        else:
            occurred_at = timezone.now()

        return {
            "priority": priority,
            "problem_type": problem_type,
            "description": body.get("description", ""),
            "reported_by_name": body.get("reported_by_name", ""),
            "occurred_at": occurred_at,
            "mark_broken": bool(body.get("mark_broken", False)),
        }
