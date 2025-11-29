"""Discord webhook message formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.urls import reverse

if TYPE_CHECKING:
    from the_flip.apps.maintenance.models import LogEntry, ProblemReport


def get_base_url() -> str:
    """Get the base URL for the site."""
    # Use SITE_URL setting if available, otherwise construct from common settings
    return getattr(settings, "SITE_URL", "https://theflip.app")


def format_discord_message(event_type: str, obj: Any) -> dict:
    """Format a Discord webhook message for the given event and object."""
    if event_type == "problem_report_created":
        return _format_problem_report_created(obj)
    elif event_type == "problem_report_closed":
        return _format_problem_report_closed(obj)
    elif event_type == "problem_report_reopened":
        return _format_problem_report_reopened(obj)
    elif event_type == "log_entry_created":
        return _format_log_entry_created(obj)
    else:
        return {"content": f"Unknown event: {event_type}"}


def _format_problem_report_created(report: ProblemReport) -> dict:
    """Format a new problem report notification."""
    base_url = get_base_url()
    url = base_url + reverse("problem-report-detail", kwargs={"pk": report.pk})

    # Build description
    lines = []
    lines.append(f"**Machine:** {report.machine.display_name}")
    if report.machine.location:
        lines.append(f"**Location:** {report.machine.location}")
    lines.append(f"**Problem:** {report.get_problem_type_display()}")
    if report.description:
        # Truncate long descriptions
        desc = report.description[:200]
        if len(report.description) > 200:
            desc += "..."
        lines.append(f"**Details:** {desc}")
    if report.reporter_display:
        lines.append(f"**Reported by:** {report.reporter_display}")

    return {
        "embeds": [
            {
                "title": "New Problem Report",
                "description": "\n".join(lines),
                "url": url,
                "color": 15158332,  # Red color for problems
            }
        ]
    }


def _format_problem_report_closed(report: ProblemReport) -> dict:
    """Format a problem report closed notification."""
    base_url = get_base_url()
    url = base_url + reverse("problem-report-detail", kwargs={"pk": report.pk})

    lines = []
    lines.append(f"**Machine:** {report.machine.display_name}")
    lines.append(f"**Problem:** {report.get_problem_type_display()}")

    return {
        "embeds": [
            {
                "title": "Problem Report Closed",
                "description": "\n".join(lines),
                "url": url,
                "color": 3066993,  # Green color for resolved
            }
        ]
    }


def _format_problem_report_reopened(report: ProblemReport) -> dict:
    """Format a problem report reopened notification."""
    base_url = get_base_url()
    url = base_url + reverse("problem-report-detail", kwargs={"pk": report.pk})

    lines = []
    lines.append(f"**Machine:** {report.machine.display_name}")
    lines.append(f"**Problem:** {report.get_problem_type_display()}")

    return {
        "embeds": [
            {
                "title": "Problem Report Reopened",
                "description": "\n".join(lines),
                "url": url,
                "color": 15105570,  # Orange color for reopened
            }
        ]
    }


def _format_log_entry_created(log_entry: LogEntry) -> dict:
    """Format a new log entry notification."""
    base_url = get_base_url()
    url = base_url + reverse("log-detail", kwargs={"pk": log_entry.pk})

    lines = []
    lines.append(f"**Machine:** {log_entry.machine.display_name}")

    # Get maintainers
    maintainer_names = []
    for m in log_entry.maintainers.all():
        maintainer_names.append(m.user.get_full_name() or m.user.username)
    if log_entry.maintainer_names:
        maintainer_names.append(log_entry.maintainer_names)
    if maintainer_names:
        lines.append(f"**By:** {', '.join(maintainer_names)}")

    # Work date
    lines.append(f"**Date:** {log_entry.work_date.strftime('%b %d, %Y')}")

    # Work description (truncate if needed)
    text = log_entry.text[:300]
    if len(log_entry.text) > 300:
        text += "..."
    lines.append(f"**Work:** {text}")

    # If linked to a problem report
    if log_entry.problem_report:
        lines.append(f"**Related Problem:** {log_entry.problem_report.get_problem_type_display()}")

    return {
        "embeds": [
            {
                "title": "Work Logged",
                "description": "\n".join(lines),
                "url": url,
                "color": 3447003,  # Blue color for work logs
            }
        ]
    }


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    event_labels = {
        "problem_report_created": "Problem Report Created",
        "problem_report_closed": "Problem Report Closed",
        "problem_report_reopened": "Problem Report Reopened",
        "log_entry_created": "Log Entry Created",
    }
    label = event_labels.get(event_type, event_type)

    return {
        "embeds": [
            {
                "title": f"Test: {label}",
                "description": (
                    "This is a test message from The Flip maintenance system.\n\n"
                    "**Machine:** Test Machine\n"
                    "**Location:** Test Location\n"
                    "**Details:** This confirms your webhook is working correctly."
                ),
                "color": 7506394,  # Purple color for test
            }
        ]
    }
