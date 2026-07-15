"""Rules coupling problem-report priority to machine operational status.

The invariant enforced here: **an open ``Unplayable`` problem report means the
machine is ``Broken``.**  The coupling is deliberately *one-directional* — we
mark a machine broken automatically, but never un-break it automatically, since
a machine can be broken for reasons unrelated to any report.  Returning a
machine to service is a human decision, surfaced by
:func:`machine_status_downgrade_prompt`.

Both functions operate on real models and are called from views/APIs.  The
one-time backfill that reconciles pre-existing discrepancies lives in
:mod:`flipfix.apps.maintenance.reconcile_machine_status`, which takes the app
registry so it runs unchanged in a data migration (frozen models) and its test
(real models) — the same split used by
:mod:`flipfix.apps.maintenance.deduplication`.
"""

from __future__ import annotations

from django.db.models import Count

from flipfix.apps.catalog.models import MachineInstance

from .models import ProblemReport


def enforce_unplayable_breaks_machine(report: ProblemReport, *, actor=None) -> bool:
    """Mark ``report``'s machine broken if the report is open and unplayable.

    Idempotent and one-directional: only ever sets ``Broken`` and never clears
    it.  Pass ``actor`` (the user making the change) so the automatic
    "Status changed" log entry created by the ``MachineInstance`` post_save
    signal is attributed correctly.  Returns ``True`` if the machine's status
    was changed.
    """
    if report.status != ProblemReport.Status.OPEN:
        return False
    if report.priority != ProblemReport.Priority.UNPLAYABLE:
        return False

    machine = report.machine
    if machine.operational_status == MachineInstance.OperationalStatus.BROKEN:
        return False

    machine.operational_status = MachineInstance.OperationalStatus.BROKEN
    update_fields = ["operational_status", "updated_at"]
    if actor is not None:
        machine.updated_by = actor
        update_fields.append("updated_by")
    machine.save(update_fields=update_fields)
    return True


def machine_status_downgrade_prompt(closed_report: ProblemReport) -> dict | None:
    """Return a "set machine to Good?" prompt after closing the last unplayable report.

    Returns ``None`` unless ``closed_report`` is a now-closed ``Unplayable``
    report whose machine is currently ``Broken`` and has no remaining open
    ``Unplayable`` reports — i.e. the maintainer just resolved the reason the
    machine was broken.  The caller is responsible for offering the action; we
    only build the summary.
    """
    if closed_report.priority != ProblemReport.Priority.UNPLAYABLE:
        return None
    if closed_report.status != ProblemReport.Status.CLOSED:
        return None

    machine = closed_report.machine
    if machine.operational_status != MachineInstance.OperationalStatus.BROKEN:
        return None

    open_reports = machine.problem_reports.filter(status=ProblemReport.Status.OPEN)
    if open_reports.filter(priority=ProblemReport.Priority.UNPLAYABLE).exists():
        return None

    breakdown = _open_priority_breakdown(open_reports)
    remaining = sum(item["count"] for item in breakdown)
    return {
        "message": _downgrade_prompt_message(remaining, breakdown),
        "remaining_open": remaining,
        "breakdown": breakdown,
        "machine_slug": machine.slug,
    }


def _open_priority_breakdown(open_reports) -> list[dict]:
    """Count open reports per priority, ordered by ``Priority`` enum position."""
    counts = {
        row["priority"]: row["count"]
        for row in open_reports.values("priority").annotate(count=Count("id"))
    }
    return [
        {"priority": value, "label": label, "count": counts[value]}
        for value, label in ProblemReport.Priority.choices
        if counts.get(value)
    ]


def _downgrade_prompt_message(remaining: int, breakdown: list[dict]) -> str:
    """Render the prompt sentence, e.g. 'Last Unplayable report closed. …'."""
    if remaining == 0:
        return "Last Unplayable report closed. No open reports remain. Set machine to Good?"
    detail = ", ".join(f"{item['count']} {item['label']}" for item in breakdown)
    noun = "report" if remaining == 1 else "reports"
    return (
        f"Last Unplayable report closed. {remaining} open {noun} remain "
        f"({detail}). Set machine to Good?"
    )
