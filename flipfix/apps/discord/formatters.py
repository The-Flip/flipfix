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

from flipfix.apps.core.markdown_links import render_all_links

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from flipfix.apps.accounts.models import Maintainer

# Discord's hard ceiling for an embed description.
DISCORD_POST_DESCRIPTION_MAX_CHARS = 4096

# Notifications summarise; they are not the record. Cap the body so a long entry
# (e.g. a pasted intake checklist) doesn't fill several screens — the title always
# links to the full record. Generous enough that a real repair write-up survives
# whole; the longest genuine log entry in production history is ~450 words.
NOTIFICATION_BODY_MAX_WORDS = 500

# How much of a related record (a linked problem report, a part's name) fits on
# one line before it stops being scannable.
SUMMARY_MAX_CHARS = 50

# How many "also in this session" lines a post carries. Each runs to roughly 145
# characters with its link, so this keeps the suffix clear of the 4,096-character
# description limit even before the body is added. See _fit_followups.
FOLLOWUP_MAX_LINES = 20


_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def _truncate_words(text: str, max_words: int) -> str:
    """Trim ``text`` to at most ``max_words`` words, cutting on a word boundary.

    Preserves the original spacing and Markdown of the kept portion (only the
    tail is dropped) and appends an ellipsis when anything was removed. If the
    cut would fall inside a Markdown link ``[label](url)`` (whose multi-word
    label could otherwise be sliced apart), it extends to the link's end so the
    link stays intact.
    """
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text
    kept = 0
    for match in re.finditer(r"\S+", text):
        kept += 1
        if kept == max_words:
            cut = match.end()
            for link in _MARKDOWN_LINK.finditer(text):
                if link.start() < cut < link.end():
                    cut = link.end()
                    break
            return text[:cut].rstrip() + "…"
    return text


_URL = re.compile(r"https?://\S+")


def summarize(text: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """Flatten ``text`` onto one line and trim it to ``max_chars``.

    Used where a record is mentioned inside another record's message, so a
    multi-line description doesn't push the real content off the screen.
    """
    flattened = " ".join((text or "").split())
    if len(flattened) <= max_chars:
        return flattened
    return flattened[:max_chars].rstrip() + "..."


def part_name(text: str, max_chars: int = 60) -> str:
    """Name the part a request is about, without its shopping links.

    Parts requests are usually "what I need" followed by a supplier URL. The URL
    is the least useful thing to spend a summary line on, and a raw link in a
    Discord embed also drags an unwanted preview card along with it.
    """
    rendered = render_all_links(text or "", plain_text=True)
    return summarize(_URL.sub("", rendered), max_chars) or "(unnamed part)"


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
    followups: list[str] | None = None,
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
        followups: Optional one-per-line summaries of the rest of the same work
            session — the status change and the move to the floor that went with
            this repair. Listed below the attribution.

    Returns:
        Dict ready for Discord webhook payload with "embeds" key.
    """
    # A notification summarises; cap the body so long entries don't dominate the
    # channel (the title links to the full record).
    record_description = _truncate_words(record_description, NOTIFICATION_BODY_MAX_WORDS)

    # Build the suffix that must be preserved (linked record, attribution, followups)
    suffix_parts = []
    if linked_record:
        suffix_parts.append(linked_record)
    suffix_parts.append(f"— {user_attribution}")
    if followups:
        suffix_parts.append("\n".join(_fit_followups(followups)))
    suffix = "\n\n".join(suffix_parts)

    # Calculate available space for record_description
    # Safety margin of 5 chars to prevent off-by-one errors
    # Account for "\n\n" separator between description and suffix
    separator = "\n\n"
    available = DISCORD_POST_DESCRIPTION_MAX_CHARS - 5 - len(suffix) - len(separator)

    # Truncate record_description if needed. A suffix long enough to fill the
    # embed on its own leaves nothing for the body: max(0, …) keeps the slice
    # from running backwards from the end and smuggling the whole body through.
    if len(record_description) > available:
        record_description = record_description[: max(available - 3, 0)]
        record_description = record_description + "..." if record_description else ""

    # Combine into final description
    description = record_description + separator + suffix if record_description else suffix

    # Build the main embed
    main_embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "url": title_url,
        "color": color,
    }

    return {"embeds": _build_gallery_embeds(main_embed, photos, title_url, base_url, color)}


def _fit_followups(followups: list[str]) -> list[str]:
    """Bound the follow-up list so the embed cannot exceed Discord's limit.

    A session on one machine can hold dozens of records, and each follow-up line
    runs to roughly 145 characters once its link is attached. Left unbounded they
    fill the 4,096-character description on their own, Discord rejects the post
    with a 400, and because the flush only marks rows sent on success the whole
    group retries every minute forever.

    Listing every record is not worth that, so keep the first
    ``FOLLOWUP_MAX_LINES`` and say plainly how many were left out — the reader
    can still open the machine to see the rest.
    """
    if len(followups) <= FOLLOWUP_MAX_LINES:
        return followups
    hidden = len(followups) - FOLLOWUP_MAX_LINES
    return [*followups[:FOLLOWUP_MAX_LINES], f"…and {hidden} more on this machine"]


def get_actor_display_name(user: Any) -> str:
    """Best display name for a user in a coalesced message (Discord name if linked)."""
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


# Discord colour for the combined summary message (blue, matching log entries).
DIGEST_COLOR = 3447003


def build_followup_line(text: str, url: str | None = None) -> str:
    """One line describing a record folded into somebody else's post.

    Routine actions ("Status changed: Unknown → Good") read as plain sentences —
    linking them adds noise for a page nobody needs. Anything a person wrote gets
    a link so the full record is one click away.
    """
    flattened = _sanitize_link_text(text)
    return f"[{flattened}]({url})" if url else flattened


def build_sweep_message(
    *,
    actor_name: str,
    sections: list[tuple[str, list[str]]],
    total: int,
) -> dict:
    """Build one message summarising a stretch of routine record-keeping.

    Grouped by *action* rather than by machine: somebody moving fifteen machines
    onto the floor wants one "Moved to the floor" heading with fifteen names
    under it, not fifteen headings with one line each.

    Args:
        actor_name: Display name of the person whose activity this summarises.
        sections: ``(action_label, [entry, ...])`` groups, in display order.
        total: Total number of records summarised (for the header count).

    Returns:
        Dict ready for a Discord webhook payload with an ``embeds`` key.
    """
    blocks = [f"**{label}**\n{', '.join(entries)}" for label, entries in sections]
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
