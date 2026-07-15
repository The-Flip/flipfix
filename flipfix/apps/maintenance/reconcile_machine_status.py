"""One-time reconciliation of the Unplayable → Broken invariant.

Historically a machine's ``operational_status`` and its problem reports drifted
apart, so a machine could show ``Good`` while carrying an open ``Unplayable``
report.  :func:`reconcile_unplayable_machine_status` brings existing rows into
line with the rule now enforced at write time by
:mod:`flipfix.apps.maintenance.status_rules`.

The entry point takes the Django ``apps`` registry rather than concrete model
classes so it runs unchanged against the frozen models inside a data migration
(the ``apps`` handed to ``RunPython``) and the real models from a test
(``from django.apps import apps``) — mirroring
:mod:`flipfix.apps.maintenance.deduplication`.
"""

from __future__ import annotations

from collections.abc import Callable

# Literal choice values (frozen models don't expose the TextChoices helpers).
# These mirror MachineInstance.OperationalStatus and ProblemReport.Status/Priority.
_BROKEN = "broken"
_OPEN = "open"
_UNPLAYABLE = "unplayable"

_CLEANUP_LOG_TEXT = "Status set to Broken to match an open Unplayable report (automated cleanup)"


def reconcile_unplayable_machine_status(apps, *, log: Callable[[str], None] = print) -> dict:
    """Mark every machine with an open Unplayable report as Broken.

    One-directional: machines that are Broken *without* an open Unplayable
    report are left untouched (they may be broken for other reasons).  Each
    machine fixed here gets a documenting ``LogEntry`` so the change is visible
    on the timeline.  Deliberately does **not** write a
    ``HistoricalMachineInstance`` row — this is a data cleanup, not a user
    action.  Returns and logs an ``{"updated": n}`` summary.
    """
    machine_instance = apps.get_model("catalog", "MachineInstance")
    problem_report = apps.get_model("maintenance", "ProblemReport")
    log_entry = apps.get_model("maintenance", "LogEntry")

    machine_ids = (
        problem_report.objects.filter(status=_OPEN, priority=_UNPLAYABLE)
        .values_list("machine_id", flat=True)
        .distinct()
    )
    drifted = machine_instance.objects.filter(id__in=machine_ids).exclude(
        operational_status=_BROKEN
    )

    updated = 0
    for machine in drifted:
        machine.operational_status = _BROKEN
        machine.save(update_fields=["operational_status", "updated_at"])
        log_entry.objects.create(machine=machine, text=_CLEANUP_LOG_TEXT, created_by=None)
        updated += 1

    log(f"reconcile_unplayable_machine_status: marked {updated} machine(s) broken")
    return {"updated": updated}
