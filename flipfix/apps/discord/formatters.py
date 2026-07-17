"""Discord webhook message formatting utilities.

Shared helpers used by webhook handler classes to build Discord embeds.
The per-type formatting logic lives in each webhook handler's
format_webhook_message() method.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import TYPE_CHECKING, Any

from django.conf import settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from flipfix.apps.accounts.models import Maintainer

# Discord's hard ceiling for an embed description.
DISCORD_POST_DESCRIPTION_MAX_CHARS = 4096

# Notifications summarise; they are not the record. Cap the body at roughly a
# couple hundred words so a long entry (e.g. a pasted intake checklist) doesn't
# fill several screens — the title always links to the full record.
NOTIFICATION_BODY_MAX_WORDS = 200


def _truncate_words(text: str, max_words: int) -> str:
    """Trim ``text`` to at most ``max_words`` words, cutting on a word boundary.

    Preserves the original spacing and Markdown of the kept portion (only the
    tail is dropped) and appends an ellipsis when anything was removed.
    """
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text
    # Walk to the end of the max_words-th word to keep the original substring.
    kept = 0
    for match in re.finditer(r"\S+", text):
        kept += 1
        if kept == max_words:
            return text[: match.end()].rstrip() + "…"
    return text


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
            from flipfix.apps.discord.models import DiscordUserLink

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
    # A notification summarises; cap the body to a couple hundred words so long
    # entries don't dominate the channel (the title links to the full record).
    record_description = _truncate_words(record_description, NOTIFICATION_BODY_MAX_WORDS)

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


def get_actor_display_name(user: Any) -> str:
    """Best display name for a user in a coalesced digest (Discord name if linked)."""
    maintainer = getattr(user, "maintainer", None)
    if maintainer is not None:
        return get_maintainer_display_name(maintainer)
    return user.get_full_name() or user.get_username()


def _sanitize_link_text(text: str) -> str:
    """Flatten text so it is safe inside a Markdown ``[text](url)`` link.

    Collapses whitespace and neutralises the brackets that would otherwise
    terminate the link, and truncates to keep digest lines scannable.
    """
    flattened = " ".join(text.split())
    flattened = flattened.replace("[", "(").replace("]", ")")
    if len(flattened) > 80:
        flattened = flattened[:79].rstrip() + "…"
    return flattened or "(no description)"


# Discord colour for the combined per-actor digest (blue, matching log entries).
DIGEST_COLOR = 3447003


def build_actor_digest(
    *,
    actor_name: str,
    sections: list[tuple[str, list[tuple[str, str, str]]]],
    total: int,
) -> dict:
    """Build one combined Discord message summarising an actor's buffered events.

    Args:
        actor_name: Display name of the person whose activity this summarises.
        sections: ``(machine_label, [(emoji, text, url), ...])`` groups, in display
            order. Each event becomes one linked line under its machine heading.
        total: Total number of events summarised (for the header count).

    Returns:
        Dict ready for a Discord webhook payload with an ``embeds`` key.
    """
    blocks = []
    for label, events in sections:
        lines = [f"{emoji} [{_sanitize_link_text(text)}]({url})" for emoji, text, url in events]
        blocks.append(f"**{label}**\n" + "\n".join(lines))
    description = "\n\n".join(blocks)

    # Reserve a little room for a truncation marker within Discord's limit.
    limit = DISCORD_POST_DESCRIPTION_MAX_CHARS - 2
    if len(description) > limit:
        description = description[: limit - 1].rstrip() + "…"

    noun = "update" if total == 1 else "updates"
    return {
        "embeds": [
            {
                "title": f"🔧 {actor_name} — {total} {noun}",
                "description": description,
                "color": DIGEST_COLOR,
            }
        ]
    }


def format_test_message(event_type: str) -> dict:
    """Format a test message for a given event type."""
    from flipfix.apps.discord.webhook_handlers import get_webhook_handler_by_event

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
