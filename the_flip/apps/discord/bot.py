"""Discord bot for processing maintenance messages."""

from __future__ import annotations

import logging

import discord
from asgiref.sync import sync_to_async
from constance import config
from django.utils import timezone

logger = logging.getLogger(__name__)


class MaintenanceBot(discord.Client):
    """Discord bot that listens for maintenance messages and creates tickets."""

    def __init__(self):
        # We need message content intent to read messages
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        super().__init__(intents=intents)

        self._enabled_channel_ids: set[str] = set()

    async def on_ready(self):
        """Called when the bot has connected to Discord."""
        logger.info(
            "discord_bot_connected",
            extra={
                "user": str(self.user),
                "user_id": self.user.id if self.user else None,
            },
        )

        # Load enabled channels from database
        await self._refresh_channels()

    async def _refresh_channels(self):
        """Refresh the list of enabled channels from the database."""
        from the_flip.apps.discord.models import DiscordChannel

        @sync_to_async
        def get_channels():
            return set(
                DiscordChannel.objects.filter(is_enabled=True).values_list("channel_id", flat=True)
            )

        self._enabled_channel_ids = await get_channels()
        logger.info(
            "discord_bot_channels_loaded",
            extra={"channel_count": len(self._enabled_channel_ids)},
        )

    async def on_message(self, message: discord.Message):
        """Called when a message is received."""
        # Ignore our own messages
        if message.author == self.user:
            return

        # Ignore messages from bots
        if message.author.bot:
            return

        # Check if this channel is enabled
        if str(message.channel.id) not in self._enabled_channel_ids:
            return

        # Process the message
        await self._process_message(message)

    async def _process_message(self, message: discord.Message):
        """Process a message from an enabled channel."""
        from the_flip.apps.discord.models import DiscordUserLink
        from the_flip.apps.discord.parsers import parse_message

        # Get the reply context if this is a reply
        reply_embed_url = None
        if message.reference and message.reference.message_id:
            try:
                ref_message = await message.channel.fetch_message(message.reference.message_id)
                # If the referenced message has embeds with URLs, extract them
                if ref_message.embeds:
                    for embed in ref_message.embeds:
                        if embed.url:
                            reply_embed_url = embed.url
                            break
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                logger.warning(
                    "discord_fetch_reference_failed",
                    extra={"message_id": message.id, "error": str(e)},
                )

        # Parse the message
        @sync_to_async
        def do_parse():
            return parse_message(
                content=message.content,
                reply_to_embed_url=reply_embed_url,
            )

        result = await do_parse()

        # Log the parse result
        log_extra = {
            "message_id": str(message.id),
            "author_id": str(message.author.id),
            "author_name": message.author.name,
            "action": result.action,
            "reason": result.reason,
            "confident": result.confident,
            "content_preview": message.content[:100],
        }

        if result.action == "ignore":
            logger.info("discord_message_ignored", extra=log_extra)
            return

        # Look up the Discord user link
        @sync_to_async
        def get_user_link():
            return (
                DiscordUserLink.objects.select_related("maintainer__user")
                .filter(discord_user_id=str(message.author.id))
                .first()
            )

        user_link = await get_user_link()

        if not user_link:
            log_extra["ignore_reason"] = "no_user_link"
            logger.info("discord_message_ignored", extra=log_extra)
            return

        # Update cached Discord user info if changed
        await self._update_user_info(user_link, message.author)

        # Create the appropriate record
        if result.action == "log_entry":
            await self._create_log_entry(message, result, user_link)
        elif result.action == "problem_report":
            await self._create_problem_report(message, result, user_link)
        elif result.action == "part_request":
            await self._create_part_request(message, result, user_link)
        elif result.action == "part_request_update":
            await self._create_part_request_update(message, result, user_link)

    @sync_to_async
    def _update_user_info(self, user_link, author: discord.Member | discord.User):
        """Update cached Discord user info if it has changed."""
        changed = False

        if user_link.discord_username != author.name:
            user_link.discord_username = author.name
            changed = True

        display_name = getattr(author, "display_name", author.name)
        if user_link.discord_display_name != display_name:
            user_link.discord_display_name = display_name
            changed = True

        avatar_url = str(author.display_avatar.url) if author.display_avatar else ""
        if user_link.discord_avatar_url != avatar_url:
            user_link.discord_avatar_url = avatar_url
            changed = True

        if changed:
            user_link.save(
                update_fields=[
                    "discord_username",
                    "discord_display_name",
                    "discord_avatar_url",
                    "updated_at",
                ]
            )

    @sync_to_async
    def _create_log_entry(self, message: discord.Message, result, user_link):
        """Create a LogEntry from a Discord message."""
        from the_flip.apps.maintenance.models import LogEntry

        log_entry = LogEntry.objects.create(
            machine=result.machine,
            problem_report=result.problem_report,
            text=message.content,
            work_date=timezone.now(),
            created_by=user_link.maintainer.user,
        )
        log_entry.maintainers.add(user_link.maintainer)

        logger.info(
            "discord_log_entry_created",
            extra={
                "message_id": str(message.id),
                "log_entry_id": log_entry.pk,
                "machine": result.machine.display_name if result.machine else None,
                "problem_report_id": result.problem_report.pk if result.problem_report else None,
                "author": message.author.name,
            },
        )

    @sync_to_async
    def _create_problem_report(self, message: discord.Message, result, user_link):
        """Create a ProblemReport from a Discord message."""
        from the_flip.apps.maintenance.models import ProblemReport

        report = ProblemReport.objects.create(
            machine=result.machine,
            problem_type="other",
            description=message.content,
            reported_by_user=user_link.maintainer.user,
        )

        logger.info(
            "discord_problem_report_created",
            extra={
                "message_id": str(message.id),
                "problem_report_id": report.pk,
                "machine": result.machine.display_name if result.machine else None,
                "author": message.author.name,
            },
        )

    @sync_to_async
    def _create_part_request(self, message: discord.Message, result, user_link):
        """Create a PartRequest from a Discord message."""
        from the_flip.apps.parts.models import PartRequest

        part_request = PartRequest.objects.create(
            machine=result.machine,
            text=message.content,
            requested_by=user_link.maintainer,
        )

        logger.info(
            "discord_part_request_created",
            extra={
                "message_id": str(message.id),
                "part_request_id": part_request.pk,
                "machine": result.machine.display_name if result.machine else None,
                "author": message.author.name,
            },
        )

    @sync_to_async
    def _create_part_request_update(self, message: discord.Message, result, user_link):
        """Create a PartRequestUpdate from a Discord message."""
        from the_flip.apps.parts.models import PartRequestUpdate

        update = PartRequestUpdate.objects.create(
            part_request=result.part_request,
            text=message.content,
            posted_by=user_link.maintainer,
        )

        logger.info(
            "discord_part_request_update_created",
            extra={
                "message_id": str(message.id),
                "part_request_update_id": update.pk,
                "part_request_id": result.part_request.pk,
                "author": message.author.name,
            },
        )


def run_bot():
    """Run the Discord bot. Called from the management command."""
    if not config.DISCORD_BOT_ENABLED:
        logger.error("Discord bot is disabled in settings")
        return

    token = config.DISCORD_BOT_TOKEN
    if not token:
        logger.error("Discord bot token not configured")
        return

    bot = MaintenanceBot()

    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error("Invalid Discord bot token")
    except Exception as e:
        logger.exception("Discord bot error: %s", e)
