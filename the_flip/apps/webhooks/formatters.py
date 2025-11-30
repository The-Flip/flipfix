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
    elif event_type == "log_entry_created":
        return _format_log_entry_created(obj)
    else:
        return {"content": f"Unknown event: {event_type}"}


def _format_problem_report_created(report: ProblemReport) -> dict:
    """Format a new problem report notification."""
    base_url = get_base_url()
    url = base_url + reverse("problem-report-detail", kwargs={"pk": report.pk})

    # Build description: [problem type]: [description] (omit type if "Other")
    parts = []
    if report.problem_type != "other":
        parts.append(report.get_problem_type_display())
    if report.description:
        desc = report.description[:200]
        if len(report.description) > 200:
            desc += "..."
        parts.append(desc)

    description = ": ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")

    # Add reporter with em dash (default to "Visitor" if no reporter info)
    reporter = report.reporter_display or "Visitor"
    description += f"\n\n— {reporter}"

    return {
        "embeds": [
            {
                "title": f"⚠️ Problem Report on {report.machine.display_name}",
                "description": description,
                "url": url,
                "color": 15158332,  # Red color for problems
            }
        ]
    }


def _format_log_entry_created(log_entry: LogEntry) -> dict:
    """Format a new log entry notification."""
    from the_flip.apps.maintenance.models import LogEntryMedia

    base_url = get_base_url()
    url = base_url + reverse("log-detail", kwargs={"pk": log_entry.pk})

    # Main description is the log entry text (truncate if needed)
    description = log_entry.text[:500]
    if len(log_entry.text) > 500:
        description += "..."

    # If attached to a problem report, add a link
    if log_entry.problem_report:
        pr = log_entry.problem_report
        pr_url = base_url + reverse("problem-report-detail", kwargs={"pk": pr.pk})
        # Build PR text: [problem type]: [truncated description]
        pr_text_parts = []
        if pr.problem_type != "other":
            pr_text_parts.append(pr.get_problem_type_display())
        if pr.description:
            pr_desc = pr.description[:50]
            if len(pr.description) > 50:
                pr_desc += "..."
            pr_text_parts.append(pr_desc)
        pr_text = ": ".join(pr_text_parts) if pr_text_parts else ""
        # Format: 📎 Problem Report #N: [text] (hyperlink the #N)
        if pr_text:
            description += f"\n\n📎 [Problem Report #{pr.pk}]({pr_url}): {pr_text}"
        else:
            description += f"\n\n📎 [Problem Report #{pr.pk}]({pr_url})"

    # Get maintainer names
    maintainer_names = []
    for m in log_entry.maintainers.all():
        maintainer_names.append(m.user.get_full_name() or m.user.username)
    if log_entry.maintainer_names:
        maintainer_names.append(log_entry.maintainer_names)

    # Add maintainer names with a visual prefix
    if maintainer_names:
        description += f"\n\n— {', '.join(maintainer_names)}"

    # Build the main embed
    main_embed: dict[str, Any] = {
        "title": f"🗒️ Log on {log_entry.machine.display_name}",
        "description": description,
        "url": url,
        "color": 3447003,  # Blue color for work logs
    }

    # Get photo URLs (up to 4 for Discord gallery effect)
    photos = list(
        log_entry.media.filter(media_type=LogEntryMedia.TYPE_PHOTO)  # type: ignore[attr-defined]
        .exclude(file="")
        .order_by("display_order", "created_at")[:4]
    )

    embeds = []
    if photos:
        # First photo goes in the main embed
        first_photo = photos[0]
        image_url = base_url + first_photo.file.url
        main_embed["image"] = {"url": image_url}
        embeds.append(main_embed)

        # Additional photos get their own embeds with same url (creates gallery)
        for photo in photos[1:]:
            image_url = base_url + photo.file.url
            embeds.append(
                {
                    "url": url,  # Same URL links them visually in Discord
                    "image": {"url": image_url},
                    "color": 3447003,
                }
            )
    else:
        embeds.append(main_embed)

    return {"embeds": embeds}


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    event_labels = {
        "problem_report_created": "Problem Report Created",
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
