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

# Discord embed limits
DISCORD_POST_DESCRIPTION_MAX_CHARS = 4096


def get_base_url() -> str:
    """Get the base URL for the site."""
    if not hasattr(settings, "SITE_URL") or not settings.SITE_URL:
        raise ValueError("SITE_URL must be configured in settings")
    return settings.SITE_URL.rstrip("/")


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


def _make_absolute_url(base_url: str, path: str) -> str:
    """Make a URL absolute, handling both relative and absolute paths.

    If path is already absolute (starts with http:// or https://), return as-is.
    Otherwise, prepend base_url.
    """
    if path.startswith(("http://", "https://")):
        return path
    return base_url + path


def _build_gallery_embeds(
    main_embed: dict[str, Any],
    photos: list,
    url: str,
    base_url: str,
    color: int,
) -> list[dict[str, Any]]:
    """Build Discord embeds with photo gallery support.

    Discord displays up to 4 images in a gallery when multiple embeds share
    the same URL. The first photo goes in the main embed; additional photos
    get their own embeds.

    Args:
        main_embed: The primary embed with title, description, etc.
        photos: List of media objects with thumbnail_file attribute.
        url: The URL for all embeds (must match for gallery effect).
        base_url: Base URL to prepend to thumbnail paths (ignored if path is absolute).
        color: Color for additional photo embeds.

    Returns:
        List of embed dicts ready for Discord webhook payload.
    """
    if not photos:
        return [main_embed]

    # First photo goes in the main embed
    image_url = _make_absolute_url(base_url, photos[0].thumbnail_file.url)
    main_embed["image"] = {"url": image_url}
    embeds = [main_embed]

    # Additional photos get their own embeds with same URL (creates gallery)
    for photo in photos[1:]:
        image_url = _make_absolute_url(base_url, photo.thumbnail_file.url)
        embeds.append(
            {
                "url": url,
                "image": {"url": image_url},
                "color": color,
            }
        )

    return embeds


def _build_discord_embed(
    *,
    title: str,
    title_url: str,
    record_description: str,
    user_attribution: str,
    color: int,
    photos: list,
    base_url: str,
    linked_record: str | None = None,
) -> dict:
    """Build Discord webhook payload.

    Truncates record_description if needed to fit within Discord's limit,
    while preserving other fields like user_attribution and linked_record.

    Args:
        title: Title of the Discord message, e.g. "🗒️ Ballyhoo"
        title_url: Clicking the title goes here (e.g. /logs/123/)
        record_description: The record's description field (log text, PR description, etc.)
        user_attribution: Who created it: "Bob, Alice". This function adds "— " prefix
        color: Embed accent color (e.g. blue for logs, red for problems)
        photos: Up to four photos; 4 is the limit that Discord will display.
            Only photos, no videos; Discord webhooks can only contain photos.
            List of Media objects with thumbnail_file attr.
        base_url: Site URL prefix for building absolute photo URLs
        linked_record: Optional related record with link, in markdown format,
            e.g. "📎 [PR #5](url): description"

    Returns:
        Dict ready for Discord webhook payload with "embeds" key.
    """
    # Build the suffix that must be preserved (linked_record + user attribution)
    suffix_parts = []
    if linked_record:
        suffix_parts.append(linked_record)
    suffix_parts.append(f"— {user_attribution}")
    suffix = "\n\n".join(suffix_parts)

    # Calculate available space for record_description
    # Safety margin of 5 chars to prevent off-by-one errors
    # Account for "\n\n" separator between description and suffix
    separator = "\n\n"
    available = DISCORD_POST_DESCRIPTION_MAX_CHARS - 5 - len(suffix) - len(separator)

    # Truncate record_description if needed
    if len(record_description) > available:
        # Leave room for ellipsis
        record_description = record_description[: available - 3] + "..."

    # Combine into final description
    description = record_description + separator + suffix

    # Build the main embed
    main_embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "url": title_url,
        "color": color,
    }

    return {"embeds": _build_gallery_embeds(main_embed, photos, title_url, base_url, color)}


def format_discord_message(event_type: str, obj: Any) -> dict:
    """Format a Discord webhook message for the given event and object."""
    if event_type == "problem_report_created":
        return _format_problem_report_created(obj)
    elif event_type == "log_entry_created":
        return _format_log_entry_created(obj)
    elif event_type == "part_request_created":
        return _format_part_request_created(obj)
    elif event_type == "part_request_update_created":
        return _format_part_request_update_created(obj)
    else:
        return {"content": f"Unknown event: {event_type}"}


def _format_problem_report_created(report: ProblemReport) -> dict:
    """Format a new problem report notification."""
    from the_flip.apps.maintenance.models import ProblemReportMedia

    base_url = get_base_url()
    url = base_url + reverse("problem-report-detail", kwargs={"pk": report.pk})

    # Build description: [problem type]: [description] (omit type if "Other")
    parts = []
    if report.problem_type != "other":
        parts.append(report.get_problem_type_display())
    if report.description:
        parts.append(report.description)

    record_description = ": ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")

    # Get photos with thumbnails (up to 4 for Discord gallery)
    photos = list(
        report.media.filter(media_type=ProblemReportMedia.MediaType.PHOTO)
        .filter(thumbnail_file__gt="")
        .order_by("display_order", "created_at")[:4]
    )

    return _build_discord_embed(
        title=f"⚠️ {report.machine.short_display_name}",
        title_url=url,
        record_description=record_description,
        user_attribution=report.reporter_display,
        color=15158332,  # Red color for problem reports
        photos=photos,
        base_url=base_url,
    )


def _format_log_entry_created(log_entry: LogEntry) -> dict:
    """Format a new log entry notification."""
    from the_flip.apps.maintenance.models import LogEntryMedia

    base_url = get_base_url()
    url = base_url + reverse("log-detail", kwargs={"pk": log_entry.pk})

    # Build linked_record if attached to a problem report
    linked_record = None
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
            linked_record = f"📎 [Problem Report #{pr.pk}]({pr_url}): {pr_text}"
        else:
            linked_record = f"📎 [Problem Report #{pr.pk}]({pr_url})"

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

    user_attribution = ", ".join(maintainer_names) if maintainer_names else "Unknown"

    # Get photos with thumbnails (up to 4 for Discord gallery)
    photos = list(
        log_entry.media.filter(media_type=LogEntryMedia.MediaType.PHOTO)  # type: ignore[attr-defined]
        .filter(thumbnail_file__gt="")
        .order_by("display_order", "created_at")[:4]
    )

    return _build_discord_embed(
        title=f"🗒️ {log_entry.machine.short_display_name}",
        title_url=url,
        record_description=log_entry.text,
        user_attribution=user_attribution,
        color=3447003,  # Blue color for log entries
        photos=photos,
        base_url=base_url,
        linked_record=linked_record,
    )


def _format_part_request_created(part_request: PartRequest) -> dict:
    """Format a new part request notification."""
    from the_flip.apps.parts.models import PartRequestMedia

    base_url = get_base_url()
    url = base_url + reverse("part-request-detail", kwargs={"pk": part_request.pk})

    # Get user attribution (use Discord name if available, or fall back to display property)
    if part_request.requested_by:
        user_attribution = _get_maintainer_display_name(part_request.requested_by)
    else:
        user_attribution = part_request.requester_display or "Unknown"

    # Build title with machine name if available
    if part_request.machine:
        title = f"📦 Parts Request for {part_request.machine.short_display_name}"
    else:
        title = "📦 Parts Request"

    # Get photos with thumbnails (up to 4 for Discord gallery)
    photos = list(
        part_request.media.filter(media_type=PartRequestMedia.MediaType.PHOTO)
        .filter(thumbnail_file__gt="")
        .order_by("display_order", "created_at")[:4]
    )

    return _build_discord_embed(
        title=title,
        title_url=url,
        record_description=part_request.text,
        user_attribution=user_attribution,
        color=3447003,  # Blue color (same as logs)
        photos=photos,
        base_url=base_url,
    )


def _format_part_request_update_created(update: PartRequestUpdate) -> dict:
    """Format a new part request update notification."""
    from the_flip.apps.parts.models import PartRequestUpdateMedia

    base_url = get_base_url()
    url = base_url + reverse("part-request-detail", kwargs={"pk": update.part_request.pk})

    # Build linked_record for the parent parts request
    pr = update.part_request
    pr_desc = pr.text[:50]
    if len(pr.text) > 50:
        pr_desc += "..."
    linked_record = f"📎 [Parts Request #{pr.pk}]({url}): {pr_desc}"

    # Get user attribution (use Discord name if available, or fall back to display property)
    if update.posted_by:
        user_attribution = _get_maintainer_display_name(update.posted_by)
    else:
        user_attribution = update.poster_display or "Unknown"

    # Build title
    if update.part_request.machine:
        title = f"💬 Update on Parts Request for {update.part_request.machine.short_display_name}"
    else:
        title = "💬 Update on Parts Request"

    # Get photos with thumbnails (up to 4 for Discord gallery)
    photos = list(
        update.media.filter(media_type=PartRequestUpdateMedia.MediaType.PHOTO)
        .filter(thumbnail_file__gt="")
        .order_by("display_order", "created_at")[:4]
    )

    return _build_discord_embed(
        title=title,
        title_url=url,
        record_description=update.text,
        user_attribution=user_attribution,
        color=3447003,  # Blue color (same as logs)
        photos=photos,
        base_url=base_url,
        linked_record=linked_record,
    )


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    event_labels = {
        "problem_report_created": "Problem Report Created",
        "log_entry_created": "Log Entry Created",
        "part_request_created": "Parts Request Created",
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
