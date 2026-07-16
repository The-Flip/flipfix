"""Maintainer-only web landing page for the daily maintenance report.

Renders the verbose board from ``reports.build_report`` as HTML, resolving the
per-machine link targets (machine detail, driving problem report, log entry) that
the Discord digest can't carry. Maintainer-only: the route omits ``access=``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse
from django.views.generic import TemplateView

from flipfix.apps.maintenance.models import ProblemReport
from flipfix.apps.maintenance.reports import (
    EMOJI,
    STORAGE_BOX,
    MachineHealth,
    build_report,
    humanize_ago,
)

# Priority declaration order is severity order (untriaged/unplayable first).
_SEVERITY = {value: i for i, (value, _) in enumerate(ProblemReport.Priority.choices)}


@dataclass(frozen=True)
class Problem:
    label: str  # priority name, e.g. "major"
    url: str  # → problem-report-detail


@dataclass(frozen=True)
class MachineCell:
    """A machine prepared for the template, with resolved link URLs."""

    glyph: str  # health emoji, or a box for parked storage machines
    name: str
    year: int | None
    machine_url: str
    problems: list[Problem]  # every open report, most severe first, each linked
    date_text: str | None  # last-log time, shown only when there are problems
    date_url: str | None  # → log-detail for the latest log entry


def _problems(m: MachineHealth) -> list[Problem]:
    ordered = sorted(m.open_reports, key=lambda pr: _SEVERITY.get(pr[1], 99))
    return [
        Problem(label=priority, url=reverse("problem-report-detail", args=[report_id]))
        for report_id, priority in ordered
    ]


def _cell(m: MachineHealth, now, *, as_box: bool) -> MachineCell:
    has_problems = bool(m.open_reports)
    # The date is the machine's latest log entry; a machine with no problems
    # needs no date at all.
    show_date = has_problems and m.last_log_id is not None
    return MachineCell(
        glyph=STORAGE_BOX if as_box else EMOJI[m.health],
        name=m.name,
        year=m.year,
        machine_url=reverse("maintainer-machine-detail", args=[m.slug]),
        problems=_problems(m),
        date_text=humanize_ago(m.last_worked_at, now) if show_date else None,
        date_url=reverse("log-detail", args=[m.last_log_id]) if show_date else None,
    )


class DailyReportView(TemplateView):
    """The daily maintenance report as a browsable board (maintainer-only)."""

    template_name = "maintenance/daily_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = build_report()
        now = report.generated_at
        context["zones"] = [
            {
                "title": zone.title,
                "pulse": zone.pulse,
                "key": zone.key,
                "rows": [
                    {
                        "location_name": row.location_name,
                        "is_storage": row.is_storage,
                        "cells": [_cell(c, now, as_box=row.is_storage) for c in row.cells],
                    }
                    for row in zone.rows
                ],
            }
            for zone in report.zones
        ]
        context["legend"] = report.legend
        context["generated_at"] = report.generated_at
        return context
