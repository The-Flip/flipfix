"""Discord bot: Context menu + LLM architecture with sequential wizard UI."""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field

import discord
from constance import config
from discord import app_commands

from the_flip.apps.discord.llm import (
    MessageContext,
    RecordSuggestion,
    analyze_messages,
)
from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.apps.discord.records import create_record

logger = logging.getLogger(__name__)


@dataclass
class WizardResult:
    """Result of processing a suggestion in the wizard."""

    suggestion: RecordSuggestion
    action: str  # "created", "skipped"
    url: str | None = None  # URL to the created record


@dataclass
class WizardState:
    """State for the sequential wizard."""

    suggestions: list[RecordSuggestion]
    discord_user_id: str
    discord_message_id: int
    discord_username: str
    discord_display_name: str
    current_index: int = 0
    results: list[WizardResult] = field(default_factory=list)

    @property
    def current_suggestion(self) -> RecordSuggestion | None:
        """Return the suggestion currently being reviewed, or None if complete."""
        if 0 <= self.current_index < len(self.suggestions):
            return self.suggestions[self.current_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Return True if all suggestions have been processed."""
        return self.current_index >= len(self.suggestions)

    @property
    def total_count(self) -> int:
        """Return the total number of suggestions in this wizard session."""
        return len(self.suggestions)

    @property
    def step_number(self) -> int:
        """Return the 1-indexed step number for display."""
        return self.current_index + 1

    def record_result(self, action: str, url: str | None = None):
        """Record the result for the current suggestion and advance."""
        if self.current_suggestion:
            self.results.append(
                WizardResult(
                    suggestion=self.current_suggestion,
                    action=action,
                    url=url,
                )
            )
        self.current_index += 1

    @property
    def created_count(self) -> int:
        """Return how many suggestions were created as records."""
        return sum(1 for r in self.results if r.action == "created")

    @property
    def skipped_count(self) -> int:
        """Return how many suggestions were skipped by the user."""
        return sum(1 for r in self.results if r.action == "skipped")


class EditAndCreateModal(discord.ui.Modal):
    """Modal for editing description before creating."""

    description_input: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Describe the work done, problem found, or parts needed...",
        max_length=1000,
    )

    def __init__(self, parent_view: SequentialWizardView):
        suggestion = parent_view.state.current_suggestion
        title = f"Edit {_format_record_type(suggestion.record_type)}" if suggestion else "Edit"
        super().__init__(title=title[:45])  # Discord modal title limit
        self.parent_view = parent_view
        if suggestion:
            self.description_input.default = suggestion.description

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission - update description and create."""
        try:
            state = self.parent_view.state
            suggestion = state.current_suggestion

            if suggestion:
                # Update description with edited value
                suggestion.description = self.description_input.value

                result = await create_record(
                    suggestion=suggestion,
                    discord_user_id=state.discord_user_id,
                    discord_message_id=state.discord_message_id,
                    discord_username=state.discord_username,
                    discord_display_name=state.discord_display_name,
                )
                state.record_result("created", url=result.url)

            # Advance to next or show completion
            if state.is_complete:
                embed, view = self.parent_view.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = self.parent_view.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self.parent_view)

        except Exception as e:
            logger.exception("discord_edit_create_modal_error: %s", e)
            await _send_error_response(interaction, "Failed to create record.")


class CompletionView(discord.ui.View):
    """Simple view shown after wizard completes with optional link button."""

    def __init__(self, url: str | None):
        super().__init__(timeout=None)
        if url:
            # Link buttons don't need a callback - they open the URL directly
            self.add_item(
                discord.ui.Button(
                    label="View in Flipfix",
                    style=discord.ButtonStyle.link,
                    url=url,
                )
            )


class SequentialWizardView(discord.ui.View):
    """Sequential wizard that steps through each suggestion one at a time."""

    def __init__(
        self,
        suggestions: list[RecordSuggestion],
        discord_user_id: str,
        discord_message_id: int,
        discord_username: str,
        discord_display_name: str,
    ):
        super().__init__(timeout=600)  # 10 minute timeout for wizard
        self.state = WizardState(
            suggestions=suggestions,
            discord_user_id=discord_user_id,
            discord_message_id=discord_message_id,
            discord_username=discord_username,
            discord_display_name=discord_display_name,
        )
        self._update_buttons()

    def _update_buttons(self):
        """Update buttons based on state: Cancel for single, Skip for multiple."""
        is_single = self.state.total_count == 1

        # Show Cancel only for single item, Skip for multiple
        for item in list(self.children):
            if isinstance(item, discord.ui.Button):
                if item.label == "Cancel" and not is_single:
                    self.remove_item(item)
                elif item.label == "Skip" and is_single:
                    self.remove_item(item)

    def build_step_embed(self) -> discord.Embed:
        """Build the embed for the current step."""
        suggestion = self.state.current_suggestion
        if not suggestion:
            return self.build_completion_view()[0]

        record_type_display = _format_record_type(suggestion.record_type)

        # Title varies based on single vs multiple
        if self.state.total_count == 1:
            title = f"{record_type_display} — {suggestion.machine_name}"
        else:
            title = (
                f"Item {self.state.step_number} of {self.state.total_count}: {record_type_display}"
            )

        # For multiple: show machine name, then description
        # For single: just show description (machine name is in title)
        if self.state.total_count > 1:
            description = f"**{suggestion.machine_name}**\n\n{suggestion.description}"
        else:
            description = suggestion.description

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue(),
        )

        return embed

    def build_completion_view(self) -> tuple[discord.Embed, discord.ui.View]:
        """Build the completion embed and view."""
        created = [r for r in self.state.results if r.action == "created"]
        skipped = [r for r in self.state.results if r.action == "skipped"]

        if len(created) == 1:
            # Single record: inline link
            result = created[0]
            type_display = _format_record_type(result.suggestion.record_type)
            url = result.url
            embed = discord.Embed(
                description=f"Created a {type_display} on {result.suggestion.machine_name}. [View in Flipfix ➡️]({url})",
                color=discord.Color.green(),
            )
        elif created:
            # Multiple records: each with its own link
            lines = []
            for result in created:
                type_display = _format_record_type(result.suggestion.record_type)
                url = result.url
                lines.append(
                    f"• {type_display} on {result.suggestion.machine_name} — [View ➡️]({url})"
                )
            embed = discord.Embed(
                description=f"Created {len(created)} records:\n" + "\n".join(lines),
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                description="No records created.",
                color=discord.Color.greyple(),
            )

        if skipped and created:
            embed.set_footer(text=f"{len(skipped)} skipped")

        # No buttons needed - links are inline
        return embed, discord.ui.View()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel without creating (single item only)."""
        try:
            embed = discord.Embed(
                description="Cancelled.",
                color=discord.Color.greyple(),
            )
            await interaction.response.edit_message(embed=embed, view=CompletionView(None))
        except Exception as e:
            logger.exception("discord_cancel_error: %s", e)
            await _send_error_response(interaction, "Failed to cancel.")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip this suggestion (multiple items only)."""
        try:
            self.state.record_result("skipped")

            if self.state.is_complete:
                embed, view = self.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = self.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.exception("discord_skip_error: %s", e)
            await _send_error_response(interaction, "Failed to skip.")

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to edit, then create on submit."""
        try:
            modal = EditAndCreateModal(self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.exception("discord_edit_error: %s", e)
            await _send_error_response(interaction, "Failed to open editor.")

    @discord.ui.button(label="Create", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create with current description."""
        try:
            suggestion = self.state.current_suggestion
            if suggestion:
                result = await create_record(
                    suggestion=suggestion,
                    discord_user_id=self.state.discord_user_id,
                    discord_message_id=self.state.discord_message_id,
                    discord_username=self.state.discord_username,
                    discord_display_name=self.state.discord_display_name,
                )
                self.state.record_result("created", url=result.url)

            if self.state.is_complete:
                embed, view = self.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = self.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.exception("discord_create_error: %s", e)
            await _send_error_response(interaction, "Failed to create record.")


class DiscordBot(discord.Client):
    """Discord bot with context menu command for using Discord messages to create records to Flipfix."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self._on_tree_error

    async def _on_tree_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Global error handler for app commands."""
        original = error.__cause__ if isinstance(error, app_commands.CommandInvokeError) else error

        logger.exception(
            "discord_command_error",
            extra={
                "command": interaction.command.name if interaction.command else "unknown",
                "error": str(original),
                "traceback": traceback.format_exc(),
            },
        )

        await _send_error_response(
            interaction,
            "Something went wrong. Please try again.",
        )

    async def setup_hook(self):
        """Called when the bot is starting up."""
        logger.info("discord_setup_hook_called")

        try:

            @self.tree.context_menu(name="Add to Flipfix")
            async def save_to_flipfix(interaction: discord.Interaction, message: discord.Message):
                await self._handle_add_command(interaction, message)

            # Debug: log what commands are in the tree before sync
            local_commands = self.tree.get_commands()
            logger.info(
                "discord_commands_before_sync",
                extra={"commands": [c.name for c in local_commands]},
            )

            # Sync commands - guild-specific is faster and more reliable
            guild_id = await self._get_guild_id()
            logger.info("discord_guild_id", extra={"guild_id": guild_id})

            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)

                # Debug: fetch what Discord actually has registered
                registered = await self.tree.fetch_commands(guild=guild)
                logger.info(
                    "discord_bot_commands_synced",
                    extra={
                        "guild_id": guild_id,
                        "registered_commands": [c.name for c in registered],
                    },
                )
            else:
                await self.tree.sync()
                registered = await self.tree.fetch_commands()
                logger.info(
                    "discord_bot_commands_synced_globally",
                    extra={"registered_commands": [c.name for c in registered]},
                )
        except Exception as e:
            logger.exception("discord_setup_hook_error: %s", e)

    async def on_ready(self):
        """Called when the bot has connected to Discord."""
        logger.info(
            "discord_bot_connected",
            extra={
                "user": str(self.user),
                "user_id": self.user.id if self.user else None,
            },
        )

    async def _handle_add_command(self, interaction: discord.Interaction, message: discord.Message):
        """Handle the 'Add to Flipfix' context menu command."""
        logger.info(
            "discord_command_received",
            extra={
                "interaction_id": interaction.id,
                "already_responded": interaction.response.is_done(),
            },
        )

        # Check if already responded (can happen with duplicate registrations)
        if interaction.response.is_done():
            logger.warning("discord_interaction_already_acknowledged")
            return

        # MUST defer immediately - Discord only gives 3 seconds to respond
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if this message has already been processed
            if await _is_message_processed(str(message.id)):
                embed = discord.Embed(
                    title="Already Processed",
                    description="This message has already been saved to Flipfix.",
                    color=discord.Color.light_grey(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Gather context around the clicked message
            context = await self._gather_context(message)

            logger.info(
                "discord_analyzing_messages",
                extra={"message_count": len(context.messages), "target_id": message.id},
            )

            # Analyze with LLM
            result = await analyze_messages(context)

            if result.is_error:
                embed = discord.Embed(
                    title="Analysis Error",
                    description=result.error,
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            elif result.suggestions:
                logger.info(
                    "discord_suggestions_generated",
                    extra={"suggestion_count": len(result.suggestions)},
                )

                view = SequentialWizardView(
                    suggestions=result.suggestions,
                    discord_user_id=str(interaction.user.id),
                    discord_message_id=message.id,
                    discord_username=interaction.user.name,
                    discord_display_name=interaction.user.display_name,
                )
                embed = view.build_step_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="No Records Found",
                    description="No maintenance records were identified in these messages.\n\nTry selecting a message that discusses machine repairs, problems, or parts.",
                    color=discord.Color.light_grey(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("discord_add_command_error: %s", e)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Error",
                    description="Failed to analyze messages. Please try again.",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )

    async def _gather_context(self, message: discord.Message) -> MessageContext:
        """Gather context before (and including) the clicked message."""
        messages = []
        flipfix_urls = []

        try:
            # Get messages BEFORE the clicked message (not after)
            async for msg in message.channel.history(limit=30, before=message):
                messages.append(msg)
            # Always include the target message itself
            messages.append(message)
        except discord.HTTPException as e:
            logger.warning(
                "discord_gather_context_failed",
                extra={"message_id": message.id, "error": str(e)},
            )

        messages.sort(key=lambda m: m.created_at)

        # Get IDs of already-processed messages to filter them from context
        processed_ids = await _get_processed_message_ids([str(m.id) for m in messages])

        message_dicts = []
        for msg in messages:
            # Skip already-processed messages (except the target - checked earlier)
            if str(msg.id) in processed_ids and msg.id != message.id:
                continue

            # Check for Flipfix URLs in embeds
            for embed in msg.embeds:
                if embed.url and _is_flipfix_url(embed.url):
                    flipfix_urls.append(embed.url)

            message_dicts.append(
                {
                    "author": msg.author.display_name,
                    "content": msg.content,
                    "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M"),
                    "is_target": msg.id == message.id,
                }
            )

        return MessageContext(
            messages=message_dicts,
            target_message_id=message.id,
            flipfix_urls=flipfix_urls,
        )

    @staticmethod
    async def _get_guild_id() -> str:
        """Get guild ID from Constance config."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_config():
            return config.DISCORD_GUILD_ID

        return await get_config()


def _format_record_type(record_type: str) -> str:
    """Format record type for display."""
    type_labels = {
        "log_entry": "Log Entry",
        "problem_report": "Problem Report",
        "part_request": "Part Request",
    }
    return type_labels.get(record_type, record_type.replace("_", " ").title())


def _is_flipfix_url(url: str) -> bool:
    """Check if a URL is from a valid Flipfix domain."""
    from urllib.parse import urlparse

    from django.conf import settings

    valid_domains = getattr(settings, "DISCORD_VALID_DOMAINS", [])
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in valid_domains
        )
    except Exception:
        return False


async def _is_message_processed(message_id: str) -> bool:
    """Check if a Discord message has already been processed."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(DiscordMessageMapping.is_processed)(message_id)


async def _get_processed_message_ids(message_ids: list[str]) -> set[str]:
    """Get the set of message IDs that have already been processed."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def get_processed():
        return set(
            DiscordMessageMapping.objects.filter(discord_message_id__in=message_ids).values_list(
                "discord_message_id", flat=True
            )
        )

    return await get_processed()


async def _send_error_response(interaction: discord.Interaction, message: str):
    """Send an error response, handling both deferred and non-deferred states."""
    embed = discord.Embed(
        title="Error",
        description=message,
        color=discord.Color.red(),
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as e:
        logger.warning("discord_error_response_failed: %s", e)


def run_bot():
    """Run the Discord bot. Called from the management command."""
    if not config.DISCORD_BOT_ENABLED:
        logger.error("Discord bot is disabled in settings")
        return

    token = config.DISCORD_BOT_TOKEN
    if not token:
        logger.error("Discord bot token not configured")
        return

    bot = DiscordBot()

    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error("Invalid Discord bot token")
    except Exception as e:
        logger.exception("Discord bot error: %s", e)
