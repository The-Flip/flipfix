"""Discord webhook message formatters."""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.urls import reverse

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer
    from the_flip.apps.maintenance.models import LogEntry, ProblemReport
    from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


def get_base_url() -> str:
    """Get the base URL for the site."""
    if not hasattr(settings, "SITE_URL") or not settings.SITE_URL:
        raise ValueError("SITE_URL must be configured in settings")
    return settings.SITE_URL


def _get_maintainer_display_name(maintainer: Maintainer) -> str:
    """Get display name for a maintainer, preferring Discord name if linked."""
    # Check for Discord link
    discord_link = getattr(maintainer, "discord_link", None)
    if discord_link is None:
        # Try to fetch it (in case it wasn't prefetched)
        try:
            from the_flip.apps.discord.models import DiscordUserLink

            discord_link = DiscordUserLink.objects.filter(maintainer=maintainer).first()
        except Exception:
            discord_link = None

    if discord_link:
        return discord_link.discord_display_name or discord_link.discord_username

    # Fall back to maintainer's standard display name
    return maintainer.display_name


def format_discord_message(event_type: str, obj: Any) -> dict:
    """Format a Discord webhook message for the given event and object."""
    if event_type == "problem_report_created":
        return _format_problem_report_created(obj)
    elif event_type == "log_entry_created":
        return _format_log_entry_created(obj)
    elif event_type == "part_request_created":
        return _format_part_request_created(obj)
    elif event_type == "part_request_status_changed":
        return _format_part_request_status_changed(obj)
    elif event_type == "part_request_update_created":
        return _format_part_request_update_created(obj)
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

    # Get maintainer names (from explicit maintainers or fall back to created_by)
    maintainer_names = []
    for m in log_entry.maintainers.all():
        maintainer_names.append(_get_maintainer_display_name(m))
    if log_entry.maintainer_names:
        maintainer_names.append(log_entry.maintainer_names)

    # Fall back to created_by for auto-generated log entries
    if not maintainer_names and log_entry.created_by:
        # Check if created_by has a maintainer profile with discord link
        maintainer = getattr(log_entry.created_by, "maintainer", None)
        if maintainer:
            maintainer_names.append(_get_maintainer_display_name(maintainer))
        else:
            maintainer_names.append(
                log_entry.created_by.get_full_name() or log_entry.created_by.username
            )

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


def _format_part_request_created(part_request: PartRequest) -> dict:
    """Format a new part request notification."""
    base_url = get_base_url()
    url = base_url + reverse("part-request-detail", kwargs={"pk": part_request.pk})

    # Main description is the part request text (truncate if needed)
    description = part_request.text[:500]
    if len(part_request.text) > 500:
        description += "..."

    # Add machine info if linked
    if part_request.machine:
        description += f"\n\n📍 Machine: {part_request.machine.display_name}"

    # Add requester (use Discord name if available)
    requester = _get_maintainer_display_name(part_request.requested_by)
    description += f"\n\n— {requester}"

    return {
        "embeds": [
            {
                "title": f"📦 Parts Requested: #{part_request.pk}",
                "description": description,
                "url": url,
                "color": 3447003,  # Blue color (same as logs)
            }
        ]
    }


def _format_part_request_status_changed(part_request: PartRequest) -> dict:
    """Format a part request status change notification."""
    base_url = get_base_url()
    url = base_url + reverse("part-request-detail", kwargs={"pk": part_request.pk})

    status_emojis = {
        "requested": "📦",
        "ordered": "🛒",
        "received": "✅",
        "cancelled": "❌",
    }
    emoji = status_emojis.get(part_request.status, "📦")
    status_display = part_request.get_status_display()

    # Main description
    description = f"**Status:** {status_display}"

    # Add truncated text
    text_preview = part_request.text[:200]
    if len(part_request.text) > 200:
        text_preview += "..."
    description += f"\n\n{text_preview}"

    # Add machine info if linked
    if part_request.machine:
        description += f"\n\n📍 Machine: {part_request.machine.display_name}"

    return {
        "embeds": [
            {
                "title": f"{emoji} Parts Request #{part_request.pk}: {status_display}",
                "description": description,
                "url": url,
                "color": 3447003,  # Blue color (same as logs)
            }
        ]
    }


def _format_part_request_update_created(update: PartRequestUpdate) -> dict:
    """Format a new part request update notification."""
    base_url = get_base_url()
    url = base_url + reverse("part-request-detail", kwargs={"pk": update.part_request.pk})

    # Main description is the update text (truncate if needed)
    description = update.text[:500]
    if len(update.text) > 500:
        description += "..."

    # Add status change if applicable
    if update.new_status:
        status_display = update.get_new_status_display()
        description += f"\n\n**Status changed to:** {status_display}"

    # Add machine info if linked
    if update.part_request.machine:
        description += f"\n\n📍 Machine: {update.part_request.machine.display_name}"

    # Add who posted (use Discord name if available)
    poster = _get_maintainer_display_name(update.posted_by)
    description += f"\n\n— {poster}"

    return {
        "embeds": [
            {
                "title": f"💬 Update on Parts Request #{update.part_request.pk}",
                "description": description,
                "url": url,
                "color": 3447003,  # Blue color (same as logs)
            }
        ]
    }


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    event_labels = {
        "problem_report_created": "Problem Report Created",
        "log_entry_created": "Log Entry Created",
        "part_request_created": "Parts Request Created",
        "part_request_status_changed": "Parts Request Status Changed",
        "part_request_update_created": "Parts Request Update Created",
    }
    label = event_labels.get(event_type, event_type)

    base_url = get_base_url()
    static_url = getattr(settings, "STATIC_URL", "/static/")
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    image_path = static_url.rstrip("/") + "/core/images/test/test_discord_post.jpg"
    image_url = urllib.parse.urljoin(base_url, image_path)
    media_prefix = urllib.parse.urljoin(base_url, media_url)

    return {
        "embeds": [
            {
                "title": f"Test: {label}",
                "description": (
                    "This is a test message from Flipfix.\n\n"
                    "If your server URLs are configured correctly, this post should show a preview of this image: "
                    f"{image_url}\n\n"
                    "**Machine:** Test Machine\n"
                    "**Location:** Test Location\n"
                    "**Image Prefix:** "
                    f"{media_prefix} (will not be the same path as the test image above)"
                ),
                "color": 7506394,  # Purple color for test
                "image": {"url": image_url},
            }
        ]
    }
