"""Maintainer-only web landing page for the daily maintenance report.

Renders the verbose board from ``reports.build_report`` as HTML, resolving the
per-machine link targets (machine detail, driving problem report, log entry) that
the Discord digest can't carry. Maintainer-only: the route omits ``access=``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse
from django.views.generic import TemplateView

from flipfix.apps.maintenance.reports import (
    EMOJI,
    LABELS,
    STORAGE_BOX,
    MachineHealth,
    build_report,
    humanize_ago,
    state_date,
)


@dataclass(frozen=True)
class MachineCell:
    """A machine prepared for the template, with resolved link URLs."""

    row_glyph: str  # box for storage, health emoji otherwise (for the zone row)
    emoji: str  # always the real health emoji (for the per-machine list)
    name: str
    year: int | None
    status: str
    health: str
    health_label: str
    reports: str
    machine_url: str
    report_url: str | None
    duration_text: str
    duration_url: str | None


def _report_url(m: MachineHealth) -> str | None:
    if m.driving_report_id:
        return reverse("problem-report-detail", args=[m.driving_report_id])
    return None


def _duration_url(m: MachineHealth) -> str | None:
    """Where the "N ago" duration links.

    Log-based dates (being fixed, and the minor/good fallback) point at the log
    entry; report-based dates (untriaged/major, and a report-driven "down") point
    at the driving report. A "down" machine with no report — only a bare history
    status change — has no linkable entry, so the duration stays plain text.
    """
    if m.health in ("untriaged", "major", "down") and m.driving_report_id:
        return reverse("problem-report-detail", args=[m.driving_report_id])
    if m.last_log_id:
        return reverse("log-detail", args=[m.last_log_id])
    return None


def _cell(m: MachineHealth, now, *, as_box: bool) -> MachineCell:
    return MachineCell(
        row_glyph=STORAGE_BOX if as_box else EMOJI[m.health],
        emoji=EMOJI[m.health],
        name=m.name,
        year=m.year,
        status=m.status,
        health=m.health,
        health_label=LABELS[m.health],
        reports=", ".join(sorted(m.open_priorities)) or "none",
        machine_url=reverse("maintainer-machine-detail", args=[m.slug]),
        report_url=_report_url(m),
        duration_text=humanize_ago(state_date(m), now),
        duration_url=_duration_url(m),
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
