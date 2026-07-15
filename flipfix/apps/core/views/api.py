"""API endpoints for internal service consumers."""

from __future__ import annotations

import json
from uuid import UUID

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
from flipfix.apps.maintenance.models import LogEntry, ProblemReport
from flipfix.apps.maintenance.status_rules import enforce_unplayable_breaks_machine


def _load_json_body(request) -> dict:
    """Parse a request body as a JSON object.

    Raises ``ValidationError`` (rendered as 400) on malformed or non-object input.
    """
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as e:
        raise ValidationError("Request body must be valid JSON") from e
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    return body


def _parse_occurred_at(raw):
    """Parse an optional ISO-8601 ``occurred_at`` value, defaulting to now.

    Naive datetimes are made timezone-aware.  Raises ``ValidationError``
    (rendered as 400) when a value is given but cannot be parsed.
    """
    if not raw:
        return timezone.now()
    if not isinstance(raw, str):
        # parse_datetime() raises TypeError on non-strings; surface a 400, not a 500.
        raise ValidationError("Invalid occurred_at: expected an ISO-8601 datetime string")
    occurred_at = parse_datetime(raw)
    if occurred_at is None:
        raise ValidationError("Invalid occurred_at: expected an ISO-8601 datetime")
    if timezone.is_naive(occurred_at):
        occurred_at = timezone.make_aware(occurred_at)
    return occurred_at


def _parse_idempotency_key(raw) -> UUID | None:
    """Parse an optional ``idempotency_key``, returning a ``UUID`` or ``None``.

    Raises ``ValidationError`` (rendered as 400) when a value is given but is not
    a valid UUID.
    """
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError as e:
        raise ValidationError("Invalid idempotency_key: expected a UUID") from e


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
                # Repair any drift: an open unplayable report means broken.
                enforce_unplayable_breaks_machine(existing)
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
            # An open Unplayable report means the machine is broken.
            enforce_unplayable_breaks_machine(report)
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
        body = _load_json_body(request)

        priority = body.get("priority", ProblemReport.Priority.MINOR)
        if priority not in ProblemReport.Priority.values:
            raise ValidationError(f"Invalid priority: {priority!r}")

        problem_type = body.get("problem_type", ProblemReport.ProblemType.OTHER)
        if problem_type not in ProblemReport.ProblemType.values:
            raise ValidationError(f"Invalid problem_type: {problem_type!r}")

        return {
            "priority": priority,
            "problem_type": problem_type,
            "description": body.get("description", ""),
            "reported_by_name": body.get("reported_by_name", ""),
            "occurred_at": _parse_occurred_at(body.get("occurred_at")),
            "mark_broken": bool(body.get("mark_broken", False)),
        }


def _serialize_log_entry(entry: LogEntry) -> dict:
    """Serialize a LogEntry to a dict for JSON responses."""
    return {
        "id": entry.pk,
        "problem_report_id": entry.problem_report_id,
        "machine_asset_id": entry.machine.asset_id,
        "text": entry.text,
        "maintainer_names": entry.maintainer_names,
        "occurred_at": entry.occurred_at.isoformat(),
        "created_at": entry.created_at.isoformat(),
    }


@method_decorator(csrf_exempt, name="dispatch")
class ProblemReportLogEntryCreateApiView(View):
    """Write API: append a log entry to an existing problem report.

    Requires an API key with ``can_write`` enabled.  Lets services such as
    juice record a *recurrence* (e.g. shutting an already-broken machine down
    again) on a report that the idempotent problem-report endpoint returned
    without creating anything new.
    """

    @json_api_view
    def post(self, request, pk: int):
        api_key = validate_api_key(request, require_write=True)

        try:
            report = ProblemReport.objects.select_related("machine").get(pk=pk)
        except ProblemReport.DoesNotExist as e:
            raise Http404(f"Problem report with ID '{pk}' not found") from e

        body = _load_json_body(request)

        text = str(body.get("text", "")).strip()
        if not text:
            raise ValidationError("text is required")

        # reported_by_name maps to LogEntry.maintainer_names.  Fall back to the
        # key's app_name so the model's "a maintainer or a name is required"
        # invariant holds and the entry always carries attribution.
        maintainer_names = str(body.get("reported_by_name", "")).strip() or api_key.app_name
        max_name_length = LogEntry._meta.get_field("maintainer_names").max_length or 120
        if len(maintainer_names) > max_name_length:
            raise ValidationError(
                f"reported_by_name is too long (max {max_name_length} characters)"
            )

        idempotency_key = _parse_idempotency_key(body.get("idempotency_key"))

        # A retried request (slow or timed-out connection) reuses the same key, so
        # create_or_reuse collapses it onto the first entry instead of appending a
        # duplicate.  Mirrors the idempotent problem-report create endpoint:
        # existing match -> 200, new entry -> 201.
        with transaction.atomic():
            entry, created = LogEntry.objects.create_or_reuse(
                idempotency_key,
                machine=report.machine,
                problem_report=report,
                text=text,
                occurred_at=_parse_occurred_at(body.get("occurred_at")),
                maintainer_names=maintainer_names,
            )

        # submission_id is globally unique, so a key reused across reports would
        # silently return the wrong report's entry.  Reject that explicitly.
        if not created and entry.problem_report_id != report.pk:
            raise ValidationError("idempotency_key was already used for a different problem report")

        status = 201 if created else 200
        return JsonResponse({"log_entry": _serialize_log_entry(entry)}, status=status)
