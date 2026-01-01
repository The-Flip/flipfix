"""Context gathering for Discord bot message analysis.

Gathers messages from Discord channels with awareness of:
- Thread messages (nested inside thread starter)
- Reply chains (following message.reference back to origin)
- Webhook embeds (parsed into flipfix_record structures)

Webhook embeds are Discord embeds posted by the Flipfix webhook system when
records are created - they contain URLs linking back to the source record.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import discord
from asgiref.sync import sync_to_async

from the_flip.apps.core.media import ALLOWED_MEDIA_EXTENSIONS
from the_flip.apps.discord.llm import RecordType
from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.apps.discord.types import DiscordUserInfo

logger = logging.getLogger(__name__)

# Context gathering limits
# These balance LLM context window size (~100k tokens) with processing time and API costs.
# - MAX_THREAD_MESSAGES: Discord threads can have thousands of messages; we cap at 50
# - MAX_TOTAL_MESSAGES: Total context sent to LLM; 100 messages ≈ 10-20k tokens
# - PREROLL_MESSAGE_COUNT: Messages before thread/reply origin for additional context
# - DEFAULT_CONTEXT_MESSAGES: For simple (non-thread, non-reply) message gathering
MAX_THREAD_MESSAGES = 50
MAX_TOTAL_MESSAGES = 100
PREROLL_MESSAGE_COUNT = 10
DEFAULT_CONTEXT_MESSAGES = 30

# When truncating, allocate ~25% of budget to preroll messages.
# This prioritizes the actual conversation (thread/reply chain) over background context.
PREROLL_BUDGET_RATIO = 0.25


@dataclass
class FlipfixRecord:
    """A Flipfix record parsed from a webhook embed."""

    record_type: RecordType
    record_id: int
    machine_id: str | None = None


@dataclass
class ContextMessage:
    """A Discord message with metadata for LLM context."""

    id: str
    author: str
    content: str
    timestamp: str
    author_id: str | None = None  # Discord user ID (None for webhook embeds)
    is_target: bool = False
    reply_to_id: str | None = None
    flipfix_record: FlipfixRecord | None = None
    thread: list[ContextMessage] = field(default_factory=list)
    is_processed: bool = False  # True for placeholder messages (e.g., filtered thread starters)
    attachments: list[discord.Attachment] = field(default_factory=list)  # Media attachments


@dataclass
class GatheredContext:
    """Context gathered from Discord for LLM analysis."""

    messages: list[ContextMessage]
    target_message_id: str
    author_id_map: dict[str, DiscordUserInfo] = field(default_factory=dict)
    message_timestamp_map: dict[str, datetime] = field(default_factory=dict)
    truncated: bool = False  # True if messages were truncated due to limits


# =============================================================================
# Main Entry Point
# =============================================================================


async def gather_context(message: discord.Message) -> GatheredContext:
    """Gather context around the clicked message.

    Context gathering algorithm:
    1. If message is in a thread: fetch thread + thread starter + preroll
    2. If message is a reply: follow chain back + preroll + messages between
    3. Otherwise: fetch ~30 messages before clicked message

    For all cases, webhook embeds are parsed for flipfix_record info.
    """
    if _is_thread_message(message):
        return await _gather_thread_context(message)
    elif message.reference:
        return await _gather_reply_chain_context(message)
    else:
        return await _gather_simple_context(message)


def _is_thread_message(message: discord.Message) -> bool:
    """Check if message is inside a thread."""
    return isinstance(message.channel, discord.Thread)


# =============================================================================
# Thread Context Gathering
# =============================================================================


async def _gather_thread_context(message: discord.Message) -> GatheredContext:
    """Gather context for a message in a thread."""
    if not isinstance(message.channel, discord.Thread):
        return await _gather_simple_context(message)

    thread = message.channel

    # Fetch all raw messages
    thread_messages, thread_truncated = await _fetch_thread_messages(thread, message)
    thread_starter = await _fetch_thread_starter(thread)
    # thread.parent is ForumChannel | TextChannel | None, all Messageable
    preroll_messages = await _fetch_preroll_messages(
        thread.parent,  # type: ignore[arg-type]
        before=thread_starter,
    )

    # Apply truncation if needed
    thread_messages, preroll_messages, context_truncated = _truncate_thread_messages(
        thread_messages=thread_messages,
        preroll_messages=preroll_messages,
        has_starter=thread_starter is not None,
        target_id=message.id,
    )
    truncated = thread_truncated or context_truncated

    # Filter out already-processed messages
    all_raw = preroll_messages + ([thread_starter] if thread_starter else [])
    all_raw.extend(thread_messages)
    processed_ids = await _get_processed_message_ids([str(m.id) for m in all_raw])

    # Build author and timestamp maps from all raw messages
    author_id_map = _build_author_id_map(all_raw)
    message_timestamp_map = _build_message_timestamp_map(all_raw)

    # Build context messages
    context_messages = _build_thread_context_messages(
        preroll_messages=preroll_messages,
        thread_starter=thread_starter,
        thread_messages=thread_messages,
        target_id=str(message.id),
        processed_ids=processed_ids,
    )

    return GatheredContext(
        messages=context_messages,
        target_message_id=str(message.id),
        author_id_map=author_id_map,
        message_timestamp_map=message_timestamp_map,
        truncated=truncated,
    )


async def _fetch_thread_messages(
    thread: discord.Thread,
    target_message: discord.Message,
) -> tuple[list[discord.Message], bool]:
    """Fetch messages from a thread up to and including the target message.

    Fetches messages BEFORE the target (historical context), then includes
    the target itself. This ensures we get the conversation leading up to
    what the user clicked, not just the most recent messages.
    """
    messages: list[discord.Message] = []
    truncated = False

    try:
        # Fetch messages before the target (limit-1 to leave room for target)
        async for msg in thread.history(limit=MAX_THREAD_MESSAGES - 1, before=target_message):
            messages.append(msg)
        if len(messages) >= MAX_THREAD_MESSAGES - 1:
            truncated = True
            logger.warning(
                "discord_thread_truncated",
                extra={"thread_id": thread.id, "limit": MAX_THREAD_MESSAGES},
            )
    except discord.HTTPException as e:
        logger.warning(
            "discord_thread_fetch_failed",
            extra={"thread_id": thread.id, "error": str(e)},
        )

    # Always include the target message
    messages.append(target_message)

    messages.sort(key=lambda m: m.created_at)
    return messages, truncated


async def _fetch_thread_starter(thread: discord.Thread) -> discord.Message | None:
    """Fetch the thread starter message from parent channel."""
    parent_channel = thread.parent

    if parent_channel and thread.starter_message:
        return thread.starter_message

    if parent_channel and isinstance(parent_channel, discord.TextChannel):
        try:
            # Thread ID equals the starter message ID
            return await parent_channel.fetch_message(thread.id)
        except discord.HTTPException as e:
            logger.warning(
                "discord_thread_starter_fetch_failed",
                extra={"thread_id": thread.id, "error": str(e)},
            )

    return None


def _truncate_thread_messages(
    thread_messages: list[discord.Message],
    preroll_messages: list[discord.Message],
    has_starter: bool,
    target_id: int,
) -> tuple[list[discord.Message], list[discord.Message], bool]:
    """Truncate thread and preroll messages to fit within MAX_TOTAL_MESSAGES.

    Truncation priority: trim preroll first, then oldest thread messages.
    Always preserves the target message.

    Returns (truncated_thread, truncated_preroll, was_truncated).
    """
    starter_count = 1 if has_starter else 0
    total = len(preroll_messages) + starter_count + len(thread_messages)

    if total <= MAX_TOTAL_MESSAGES:
        return thread_messages, preroll_messages, False

    # Calculate how many messages we can include from each source
    available_budget = MAX_TOTAL_MESSAGES - starter_count
    available_preroll = min(len(preroll_messages), PREROLL_MESSAGE_COUNT)
    allocated_preroll = min(available_preroll, int(available_budget * PREROLL_BUDGET_RATIO))
    allocated_thread = available_budget - allocated_preroll

    # Truncate thread messages, preserving target
    if len(thread_messages) > allocated_thread:
        thread_messages = _truncate_preserving_target(thread_messages, allocated_thread, target_id)

    # Truncate preroll messages (keep most recent)
    if len(preroll_messages) > allocated_preroll:
        preroll_messages = preroll_messages[-allocated_preroll:]

    logger.warning(
        "discord_thread_context_truncated",
        extra={
            "original_count": total,
            "truncated_count": len(preroll_messages) + starter_count + len(thread_messages),
            "limit": MAX_TOTAL_MESSAGES,
        },
    )

    return thread_messages, preroll_messages, True


def _truncate_preserving_target(
    messages: list[discord.Message],
    budget: int,
    target_id: int,
) -> list[discord.Message]:
    """Truncate messages to budget while always preserving the target message."""
    target_idx = next(
        (i for i, m in enumerate(messages) if m.id == target_id),
        len(messages) - 1,
    )

    if target_idx >= budget - 1:
        # Target is near end, just take most recent
        return messages[-budget:]
    else:
        # Target is early; keep target + most recent to fill budget
        result = [messages[target_idx]] + messages[-(budget - 1) :]
        result.sort(key=lambda m: m.created_at)
        return result


def _build_thread_context_messages(
    preroll_messages: list[discord.Message],
    thread_starter: discord.Message | None,
    thread_messages: list[discord.Message],
    target_id: str,
    processed_ids: set[str],
) -> list[ContextMessage]:
    """Build ContextMessage list for thread context.

    Thread messages are always nested under a parent to preserve thread structure
    for the LLM, even when the original starter message was already processed.
    """
    messages: list[ContextMessage] = []

    # Add preroll messages
    for msg in preroll_messages:
        if not _should_include_message(msg, target_id, processed_ids):
            continue
        messages.append(_build_context_message(msg, target_id=target_id))

    # Build list of thread messages to include
    thread_msgs_to_include: list[ContextMessage] = []
    for msg in thread_messages:
        if not _should_include_message(msg, target_id, processed_ids):
            continue
        thread_msgs_to_include.append(_build_context_message(msg, target_id=target_id))

    # If no thread messages to include, we're done
    if not thread_msgs_to_include:
        return messages

    # Create thread container - use actual starter if available and includable,
    # otherwise create a placeholder to preserve thread structure
    if thread_starter and _should_include_message(thread_starter, target_id, processed_ids):
        starter_ctx = _build_context_message(thread_starter, target_id=target_id)
    else:
        # Create placeholder for filtered/missing starter to preserve thread nesting.
        # This tells the LLM "these messages are from a thread discussion" even when
        # we can't show the original starter (e.g., it was already processed).
        starter_ctx = ContextMessage(
            id=str(thread_starter.id) if thread_starter else "unknown",
            author="[thread starter]",
            content="[This thread's starter message was already processed]",
            timestamp=thread_starter.created_at.isoformat() if thread_starter else "",
            is_processed=True,
        )

    starter_ctx.thread = thread_msgs_to_include
    messages.append(starter_ctx)

    return messages


# =============================================================================
# Reply Chain Context Gathering
# =============================================================================


async def _gather_reply_chain_context(message: discord.Message) -> GatheredContext:
    """Gather context for a message that is a reply."""
    # Follow reply chain back to origin
    chain = await _follow_reply_chain(message)
    origin = chain[0]

    # Fetch additional context
    preroll_messages = await _fetch_preroll_messages(message.channel, before=origin)
    between_messages = await _fetch_messages_between(
        channel=message.channel,
        after=origin,
        before=message,
        exclude_ids={m.id for m in chain},
    )

    # Combine and sort all messages
    all_messages = preroll_messages + chain[:-1] + between_messages + [message]
    all_messages.sort(key=lambda m: m.created_at)

    # Apply truncation if needed
    all_messages, truncated = _truncate_reply_chain_messages(all_messages, chain)

    # Filter out already-processed messages
    processed_ids = await _get_processed_message_ids([str(m.id) for m in all_messages])

    # Build author and timestamp maps from all raw messages
    author_id_map = _build_author_id_map(all_messages)
    message_timestamp_map = _build_message_timestamp_map(all_messages)

    # Build context messages
    context_messages: list[ContextMessage] = []
    for msg in all_messages:
        if not _should_include_message(msg, str(message.id), processed_ids):
            continue
        context_messages.append(_build_context_message(msg, target_id=str(message.id)))

    return GatheredContext(
        messages=context_messages,
        target_message_id=str(message.id),
        author_id_map=author_id_map,
        message_timestamp_map=message_timestamp_map,
        truncated=truncated,
    )


async def _follow_reply_chain(message: discord.Message) -> list[discord.Message]:
    """Follow reply chain back to origin, returning messages in order."""
    chain: list[discord.Message] = [message]
    current = message

    while current.reference and current.reference.message_id:
        try:
            if current.reference.resolved and isinstance(
                current.reference.resolved, discord.Message
            ):
                referenced = current.reference.resolved
            else:
                referenced = await message.channel.fetch_message(current.reference.message_id)
            chain.insert(0, referenced)
            current = referenced
        except discord.HTTPException as e:
            # At this point current.reference is guaranteed non-None by the while condition
            ref_id = current.reference.message_id if current.reference else None
            logger.warning(
                "discord_reply_chain_fetch_failed",
                extra={"message_id": ref_id, "error": str(e)},
            )
            break

    return chain


async def _fetch_messages_between(
    channel: discord.abc.Messageable,
    after: discord.Message,
    before: discord.Message,
    exclude_ids: set[int],
) -> list[discord.Message]:
    """Fetch messages between two messages, excluding specified IDs."""
    messages: list[discord.Message] = []

    try:
        async for msg in channel.history(limit=MAX_TOTAL_MESSAGES, after=after, before=before):
            if msg.id not in exclude_ids:
                messages.append(msg)
    except discord.HTTPException as e:
        logger.warning(
            "discord_between_fetch_failed",
            extra={"channel_id": getattr(channel, "id", "unknown"), "error": str(e)},
        )

    messages.sort(key=lambda m: m.created_at)
    return messages


def _truncate_reply_chain_messages(
    all_messages: list[discord.Message],
    chain: list[discord.Message],
) -> tuple[list[discord.Message], bool]:
    """Truncate reply chain context, prioritizing chain messages.

    Returns (truncated_messages, was_truncated).
    """
    if len(all_messages) <= MAX_TOTAL_MESSAGES:
        return all_messages, False

    # Keep all chain messages, trim others
    chain_ids = {m.id for m in chain}
    chain_msgs = [m for m in all_messages if m.id in chain_ids]
    other_msgs = [m for m in all_messages if m.id not in chain_ids]

    available = MAX_TOTAL_MESSAGES - len(chain_msgs)
    if available > 0:
        other_msgs = other_msgs[-available:]

    result = sorted(chain_msgs + other_msgs, key=lambda m: m.created_at)

    logger.warning(
        "discord_reply_chain_truncated",
        extra={"original_count": len(all_messages), "limit": MAX_TOTAL_MESSAGES},
    )

    return result, True


# =============================================================================
# Simple Context Gathering
# =============================================================================


async def _gather_simple_context(message: discord.Message) -> GatheredContext:
    """Gather simple context (no thread, no reply chain)."""
    raw_messages: list[discord.Message] = []

    try:
        async for msg in message.channel.history(limit=DEFAULT_CONTEXT_MESSAGES, before=message):
            raw_messages.append(msg)
        raw_messages.append(message)
    except discord.HTTPException as e:
        logger.warning(
            "discord_context_fetch_failed",
            extra={"channel_id": message.channel.id, "error": str(e)},
        )
        raw_messages = [message]

    raw_messages.sort(key=lambda m: m.created_at)

    # Filter out already-processed messages
    processed_ids = await _get_processed_message_ids([str(m.id) for m in raw_messages])

    # Build author and timestamp maps from all raw messages
    author_id_map = _build_author_id_map(raw_messages)
    message_timestamp_map = _build_message_timestamp_map(raw_messages)

    context_messages: list[ContextMessage] = []
    for msg in raw_messages:
        if not _should_include_message(msg, str(message.id), processed_ids):
            continue
        context_messages.append(_build_context_message(msg, target_id=str(message.id)))

    return GatheredContext(
        messages=context_messages,
        target_message_id=str(message.id),
        author_id_map=author_id_map,
        message_timestamp_map=message_timestamp_map,
        truncated=False,
    )


# =============================================================================
# Shared Helper Functions
# =============================================================================


async def _fetch_preroll_messages(
    channel: discord.abc.Messageable | None,
    before: discord.Message | None,
    limit: int = PREROLL_MESSAGE_COUNT,
) -> list[discord.Message]:
    """Fetch preroll messages before a given message.

    Preroll provides additional context before the thread starter or reply origin.
    """
    if not channel or not before:
        return []

    if not isinstance(channel, discord.TextChannel):
        return []

    messages: list[discord.Message] = []
    try:
        async for msg in channel.history(limit=limit, before=before):
            messages.append(msg)
    except discord.HTTPException as e:
        logger.warning(
            "discord_preroll_fetch_failed",
            extra={"channel_id": channel.id, "error": str(e)},
        )

    messages.sort(key=lambda m: m.created_at)
    return messages


def _should_include_message(
    msg: discord.Message,
    target_id: str,
    processed_ids: set[str],
) -> bool:
    """Check if a message should be included in context.

    Excludes already-processed messages, UNLESS it's the target message
    (which we always include since the user explicitly clicked on it).
    """
    msg_id = str(msg.id)
    if msg_id == target_id:
        return True
    return msg_id not in processed_ids


def _build_context_message(msg: discord.Message, target_id: str) -> ContextMessage:
    """Convert a Discord message to a ContextMessage."""
    flipfix_record = None
    author = msg.author.display_name
    author_id: str | None = str(msg.author.id)
    content = msg.content

    for embed in msg.embeds:
        parsed = _parse_webhook_embed(embed)
        if parsed:
            flipfix_record, embed_author, embed_content = parsed
            if embed_author:
                author = embed_author
                # Use flipfix/ prefix for name-based author lookup
                # This distinguishes from Discord snowflake IDs (17-19 digit numbers)
                author_id = f"flipfix/{embed_author}"
            else:
                # No author in embed - can't attribute
                author_id = None
            if embed_content:
                content = embed_content
            break

    reply_to_id = None
    if msg.reference and msg.reference.message_id:
        reply_to_id = str(msg.reference.message_id)

    # Filter attachments to supported media types only
    attachments = _filter_supported_attachments(msg.attachments)

    return ContextMessage(
        id=str(msg.id),
        author=author,
        author_id=author_id,
        content=content,
        timestamp=msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        is_target=str(msg.id) == target_id,
        reply_to_id=reply_to_id,
        flipfix_record=flipfix_record,
        attachments=attachments,
    )


async def _get_processed_message_ids(message_ids: list[str]) -> set[str]:
    """Get the set of message IDs that have already been processed."""

    @sync_to_async
    def get_processed():
        return set(
            DiscordMessageMapping.objects.filter(discord_message_id__in=message_ids).values_list(
                "discord_message_id", flat=True
            )
        )

    return await get_processed()


def _build_author_id_map(messages: list[discord.Message]) -> dict[str, DiscordUserInfo]:
    """Build a mapping of author_id -> DiscordUserInfo from raw Discord messages.

    This allows looking up the original message author's info when creating records,
    enabling proper attribution to the person who wrote the message rather than
    whoever clicked the button.

    Skips bot users since their messages are webhook embeds without real authors.
    """
    author_map: dict[str, DiscordUserInfo] = {}
    for msg in messages:
        if msg.author.bot:
            continue
        author_id = str(msg.author.id)
        if author_id not in author_map:
            author_map[author_id] = DiscordUserInfo.from_message(msg)
    return author_map


def _build_message_timestamp_map(messages: list[discord.Message]) -> dict[str, datetime]:
    """Build a mapping of message_id -> timestamp from raw Discord messages.

    This allows looking up when each message was posted, so records created
    from Discord messages can have their occurred_at set to the message timestamp
    rather than the current time.

    Discord.py 2.0+ returns timezone-aware UTC datetimes, compatible with Django.
    """
    return {str(msg.id): msg.created_at for msg in messages}


def _filter_supported_attachments(
    attachments: list[discord.Attachment],
) -> list[discord.Attachment]:
    """Filter attachments to only those with supported media extensions.

    Unsupported formats (PDFs, documents, etc.) are silently ignored.
    """
    result = [a for a in attachments if Path(a.filename).suffix.lower() in ALLOWED_MEDIA_EXTENSIONS]
    if attachments:
        logger.debug(
            "discord_attachments_filtered",
            extra={
                "before_count": len(attachments),
                "after_count": len(result),
                "filenames": [a.filename for a in attachments],
            },
        )
    return result


# =============================================================================
# Webhook Embed Parsing
# =============================================================================


def _parse_webhook_embed(embed: discord.Embed) -> tuple[FlipfixRecord, str, str] | None:
    """Parse a Flipfix webhook embed.

    Webhook embeds have:
    - URL: https://flipfix.example.com/logs/123/ or /problem-reports/456/ etc.
    - Description: "Content text\\n\\n— AuthorName"

    Returns (FlipfixRecord, author, content) or None if not a Flipfix embed.
    """

    if not embed.url or not _is_flipfix_url(embed.url):
        return None

    record_info = _parse_flipfix_url(embed.url)
    if not record_info:
        return None

    record_type, record_id, machine_id = record_info
    flipfix_record = FlipfixRecord(
        record_type=record_type,
        record_id=record_id,
        machine_id=machine_id,
    )

    author = ""
    content = ""
    if embed.description:
        match = re.search(r"\n\n— (.+)$", embed.description)
        if match:
            author = match.group(1)
            content = embed.description[: match.start()]
        else:
            content = embed.description
            logger.debug(
                "discord_webhook_embed_no_author",
                extra={"description_preview": embed.description[:100]},
            )

    return flipfix_record, author, content


def _is_flipfix_url(url: str) -> bool:
    """Check if a URL matches Flipfix record URL patterns.

    We identify Flipfix URLs by their path structure (/logs/N/, /problem-reports/N/, etc.)
    rather than requiring domain configuration. This is sufficient because:
    - The path patterns are specific to Flipfix records
    - False positives are rare (random sites rarely use /problem-reports/<id>/ paths)
    - False positives fail gracefully (parent lookup returns None, link not created)
    """
    return _parse_flipfix_url(url) is not None


def _parse_flipfix_url(url: str) -> tuple[RecordType, int, str | None] | None:
    """Parse a Flipfix URL to extract record type and ID.

    Expected URL patterns (matching Django URL config):
    - /logs/123/ -> (RecordType.LOG_ENTRY, 123, None)
    - /problem-reports/456/ -> (RecordType.PROBLEM_REPORT, 456, None)
    - /parts/789/ -> (RecordType.PART_REQUEST, 789, None)

    The third element (machine_id) is always None since detail pages don't
    include machine slugs in their URLs.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        # Pattern: /logs/<id>
        match = re.match(r"/logs/(\d+)$", path)
        if match:
            return (RecordType.LOG_ENTRY, int(match.group(1)), None)

        # Pattern: /problem-reports/<id>
        match = re.match(r"/problem-reports/(\d+)$", path)
        if match:
            return (RecordType.PROBLEM_REPORT, int(match.group(1)), None)

        # Pattern: /parts/<id>
        match = re.match(r"/parts/(\d+)$", path)
        if match:
            return (RecordType.PART_REQUEST, int(match.group(1)), None)

        return None
    except Exception:
        return None
