"""Labor report views: weekly summary and drill-down detail."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone
from django.views.generic import TemplateView

from flipfix.apps.maintenance.models import LogEntry


def _parse_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD string, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _current_week_bounds() -> tuple[date, date]:
    """Return (Monday, Sunday) of the current ISO week."""
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


class LaborWeeklySummaryView(TemplateView):
    """Weekly labor totals for the last 8 weeks."""

    template_name = "maintenance/labor_report_weekly.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        # Go back 8 weeks from the start of this week
        this_week_start = today - timedelta(days=today.weekday())
        cutoff = this_week_start - timedelta(weeks=7)

        weeks = (
            LogEntry.objects.filter(occurred_at__date__gte=cutoff, time_spent__gt=0)
            .annotate(week=TruncWeek("occurred_at"))
            .values("week")
            .annotate(total_hours=Sum("time_spent"), entry_count=Count("id"))
            .order_by("-week")
        )

        # Build display list with week_start/week_end
        week_list = []
        for row in weeks:
            week_start = row["week"].date()
            week_end = week_start + timedelta(days=6)
            week_list.append(
                {
                    "week_start": week_start,
                    "week_end": week_end,
                    "total_hours": row["total_hours"],
                    "entry_count": row["entry_count"],
                }
            )

        grand_total = sum(w["total_hours"] for w in week_list)

        context.update(
            {
                "weeks": week_list,
                "grand_total": grand_total,
                "meta_description": "Weekly labor hour summary for The Flip maintenance team.",
            }
        )
        return context


class LaborDetailView(TemplateView):
    """Line-item detail of labor entries within a date range."""

    template_name = "maintenance/labor_report_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        start = _parse_date(self.request.GET.get("start"))
        end = _parse_date(self.request.GET.get("end"))

        if not start or not end:
            start, end = _current_week_bounds()

        entries = (
            LogEntry.objects.filter(
                occurred_at__date__gte=start,
                occurred_at__date__lte=end,
                time_spent__gt=0,
            )
            .select_related("machine", "machine__model")
            .prefetch_related("maintainers__user")
            .order_by("-occurred_at")
        )

        total_hours = sum(e.time_spent for e in entries)

        context.update(
            {
                "entries": entries,
                "start_date": start,
                "end_date": end,
                "total_hours": total_hours,
                "meta_description": f"Labor detail for {start} to {end}.",
            }
        )
        return context
