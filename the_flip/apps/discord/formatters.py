"""Discord webhook message formatting utilities.

Shared helpers used by webhook handler classes to build Discord embeds.
The per-type formatting logic lives in each webhook handler's
format_webhook_message() method.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING, Any

from django.conf import settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer

# Discord embed limits
DISCORD_POST_DESCRIPTION_MAX_CHARS = 4096


def get_base_url() -> str:
    """Get the base URL for the site."""
    if not hasattr(settings, "SITE_URL") or not settings.SITE_URL:
        raise ValueError("SITE_URL must be configured in settings")
    return settings.SITE_URL.rstrip("/")


def get_maintainer_display_name(maintainer: Maintainer) -> str:
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


def build_discord_embed(
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
    """Format a Discord webhook message for the given event and object.

    Delegates to the registered webhook handler for the event type.
    """
    from the_flip.apps.discord.webhook_handlers import get_webhook_handler_by_event

    handler = get_webhook_handler_by_event(event_type)
    if handler:
        return handler.format_webhook_message(obj)
    logger.warning("discord_unknown_event_type", extra={"event_type": event_type})
    return {}


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    from the_flip.apps.discord.webhook_handlers import get_webhook_handler_by_event

    handler = get_webhook_handler_by_event(event_type)
    label = handler.display_name if handler else event_type

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
