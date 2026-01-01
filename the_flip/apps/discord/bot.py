"""Discord bot: Context menu + LLM architecture with sequential wizard UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import discord
from asgiref.sync import sync_to_async
from constance import config
from discord import app_commands

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.discord.context import ContextMessage, gather_context
from the_flip.apps.discord.llm import (
    FlattenedSuggestion,
    RecordSuggestion,
    RecordType,
    analyze_gathered_context,
    flatten_suggestions,
)
from the_flip.apps.discord.media import (
    DJANGO_WEB_SERVICE_URL,
    TRANSCODING_UPLOAD_TOKEN,
    _is_video,
)
from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.apps.discord.records import create_record_with_media
from the_flip.apps.discord.types import DiscordUserInfo

logger = logging.getLogger(__name__)

# Wizard timeout in seconds (10 minutes allows time for editing multiple suggestions)
WIZARD_TIMEOUT_SECONDS = 600


@dataclass
class WizardResult:
    """Result of processing a suggestion in the wizard."""

    suggestion: RecordSuggestion
    action: str  # "created", "skipped"
    url: str | None = None  # URL to the created record


@dataclass
class WizardState:
    """State for the sequential wizard.

    Handles parent-child relationships: when a parent is created, its record ID
    is stored so children can reference it. When a parent is skipped, all its
    children are also skipped automatically.
    """

    flattened: list[FlattenedSuggestion]  # Flattened suggestions with parent links
    discord_user: DiscordUserInfo  # The button-clicker (fallback if author not found)
    discord_message_id: int
    author_id_map: dict[str, DiscordUserInfo] = field(default_factory=dict)
    message_timestamp_map: dict[str, datetime] = field(default_factory=dict)
    message_attachments: dict[str, list[discord.Attachment]] = field(default_factory=dict)
    current_index: int = 0
    results: list[WizardResult] = field(default_factory=list)
    # Maps flattened index -> created record ID (for parent linking)
    parent_record_ids: dict[int, int] = field(default_factory=dict)
    # Set of flattened indices that were skipped (including cascaded skips)
    skipped_indices: set[int] = field(default_factory=set)

    @property
    def current_flattened(self) -> FlattenedSuggestion | None:
        """Return the flattened suggestion currently being reviewed."""
        if 0 <= self.current_index < len(self.flattened):
            return self.flattened[self.current_index]
        return None

    @property
    def current_suggestion(self) -> RecordSuggestion | None:
        """Return the suggestion currently being reviewed, or None if complete."""
        flattened = self.current_flattened
        return flattened.suggestion if flattened else None

    @property
    def is_complete(self) -> bool:
        """Return True if all suggestions have been processed."""
        return self.current_index >= len(self.flattened)

    @property
    def total_count(self) -> int:
        """Return the total number of suggestions in this wizard session."""
        return len(self.flattened)

    @property
    def step_number(self) -> int:
        """Return the 1-indexed step number for display."""
        return self.current_index + 1

    def record_result(self, action: str, url: str | None = None, record_id: int | None = None):
        """Record the result for the current suggestion and advance.

        Args:
            action: "created" or "skipped"
            url: URL to the created record (for "created" action)
            record_id: ID of the created record (for parent linking)
        """
        suggestion = self.current_suggestion
        if suggestion:
            self.results.append(
                WizardResult(
                    suggestion=suggestion,
                    action=action,
                    url=url,
                )
            )

            if action == "created" and record_id is not None:
                # Store record ID for child linking
                self.parent_record_ids[self.current_index] = record_id

            if action == "skipped":
                self._cascade_skip()

        self.current_index += 1
        self._skip_cascaded_children()

    def _cascade_skip(self):
        """Mark all children of the current item as skipped."""
        parent_idx = self.current_index
        for i, item in enumerate(self.flattened):
            if item.parent_index == parent_idx:
                self.skipped_indices.add(i)

    def _skip_cascaded_children(self):
        """Auto-skip any items that were marked for cascaded skip."""
        while self.current_index < len(self.flattened):
            if self.current_index in self.skipped_indices:
                # Auto-skip this item
                suggestion = self.current_suggestion
                if suggestion:
                    self.results.append(
                        WizardResult(
                            suggestion=suggestion,
                            action="skipped",
                            url=None,
                        )
                    )
                self.current_index += 1
            else:
                break

    def get_author_id_for_current(self) -> str:
        """Get the author_id to attribute the current suggestion to.

        Returns the suggestion's author_id directly. This will be either:
        - A Discord snowflake ID (17-19 digits) for regular Discord messages
        - A "flipfix/Name" prefixed string for webhook-sourced authors

        Falls back to the button-clicker's Discord ID if author_id is missing.
        """
        suggestion = self.current_suggestion
        if suggestion and suggestion.author_id:
            return suggestion.author_id
        # Fallback to button-clicker's Discord ID
        return self.discord_user.user_id

    def get_author_display_name_for_current(self) -> str | None:
        """Get the display name of the author for the current suggestion.

        Returns None if the author is the same as the button-clicker.
        This is used to show "Attributed to X" in the wizard when someone
        is creating a record on behalf of another person.
        """
        author_id = self.get_author_id_for_current()

        # Resolve author_id to display name
        author_name: str | None
        if author_id.startswith("flipfix/"):
            author_name = author_id[len("flipfix/") :]
        else:
            discord_info = self.author_id_map.get(author_id)
            if discord_info:
                author_name = discord_info.display_name or discord_info.username
            else:
                author_name = None

        # Only show if different from button-clicker
        if author_name and author_name != self.discord_user.display_name:
            return author_name
        return None

    def get_parent_record_id_for_current(self) -> int | None:
        """Get the parent record ID for the current child suggestion.

        If the current suggestion is a child (has parent_index), returns the
        record ID of the parent that was created earlier in this wizard session.
        """
        flattened = self.current_flattened
        if flattened and flattened.parent_index is not None:
            return self.parent_record_ids.get(flattened.parent_index)
        return None

    def get_attachments_for_current(self) -> list[discord.Attachment]:
        """Get all attachments for the current suggestion's source messages."""
        suggestion = self.current_suggestion
        if not suggestion:
            return []
        attachments: list[discord.Attachment] = []
        for msg_id in suggestion.source_message_ids:
            attachments.extend(self.message_attachments.get(msg_id, []))
        return attachments

    @property
    def created_count(self) -> int:
        """Return how many suggestions were created as records."""
        return sum(1 for r in self.results if r.action == "created")

    @property
    def skipped_count(self) -> int:
        """Return how many suggestions were skipped by the user."""
        return sum(1 for r in self.results if r.action == "skipped")


class SuggestionEditorModal(discord.ui.Modal):
    """Modal for editing a suggestion's description before creating the record."""

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

                # Set parent_record_id for child suggestions
                parent_record_id = state.get_parent_record_id_for_current()
                if parent_record_id is not None:
                    suggestion.parent_record_id = parent_record_id

                result = await create_record_with_media(
                    suggestion=suggestion,
                    author_id=state.get_author_id_for_current(),
                    author_id_map=state.author_id_map,
                    message_timestamp_map=state.message_timestamp_map,
                    message_attachments=state.message_attachments,
                )
                state.record_result(
                    "created", url=result.result.url, record_id=result.result.record_id
                )

            # Advance to next or show completion
            if state.is_complete:
                embed, view = await self.parent_view.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = await self.parent_view.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self.parent_view)

        except Exception as e:
            logger.exception("discord_edit_create_modal_error", extra={"error": str(e)})
            await _send_error_response(interaction, "Failed to create record.")


class WizardCompletionView(discord.ui.View):
    """View shown after wizard completes, with optional link to created record."""

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
    """Sequential wizard that steps through each suggestion one at a time.

    Handles parent-child relationships: suggestions with children are flattened
    into separate wizard steps. When a parent is created, its record ID is stored
    so children can link to it. When a parent is skipped, children are auto-skipped.
    """

    def __init__(
        self,
        suggestions: list[RecordSuggestion],
        discord_user: DiscordUserInfo,
        discord_message_id: int,
        author_id_map: dict[str, DiscordUserInfo] | None = None,
        message_timestamp_map: dict[str, datetime] | None = None,
        message_attachments: dict[str, list[discord.Attachment]] | None = None,
    ):
        super().__init__(timeout=WIZARD_TIMEOUT_SECONDS)
        # Flatten suggestions to handle parent-child relationships
        flattened = flatten_suggestions(suggestions)
        self.state = WizardState(
            flattened=flattened,
            discord_user=discord_user,
            discord_message_id=discord_message_id,
            author_id_map=author_id_map or {},
            message_timestamp_map=message_timestamp_map or {},
            message_attachments=message_attachments or {},
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

    async def build_step_embed(self) -> discord.Embed:
        """Build the embed for the current step."""
        suggestion = self.state.current_suggestion
        if not suggestion:
            embed, _ = await self.build_completion_view()
            return embed

        record_type_display = _format_record_type(suggestion.record_type)

        # Look up machine display name (may be None for part requests)
        machine_name = await _get_machine_name(suggestion.slug)

        # Title varies based on single vs multiple, and whether machine is present
        if self.state.total_count == 1:
            if machine_name:
                title = f"{record_type_display} — {machine_name}"
            else:
                title = record_type_display
        else:
            title = (
                f"Item {self.state.step_number} of {self.state.total_count}: {record_type_display}"
            )

        # For multiple: show machine name (if present), then description
        # For single: just show description (machine name is in title)
        if self.state.total_count > 1 and machine_name:
            description = f"**{machine_name}**\n\n{suggestion.description}"
        else:
            description = suggestion.description

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue(),
        )

        # Build footer with parent link, author attribution, and media counts
        footer_parts = []
        if suggestion.parent_record_id:
            parent_type = _get_parent_type_label(suggestion.record_type)
            footer_parts.append(f"🔗 Links to {parent_type} #{suggestion.parent_record_id}")

        author_name = self.state.get_author_display_name_for_current()
        if author_name:
            footer_parts.append(f"👤 Attributed to {author_name}")

        media_counts = _format_media_counts(self.state.get_attachments_for_current())
        if media_counts:
            footer_parts.append(f"🏞️ {media_counts}")

        if footer_parts:
            embed.set_footer(text="\n".join(footer_parts))

        return embed

    async def build_completion_view(self) -> tuple[discord.Embed, discord.ui.View]:
        """Build the completion embed and view."""
        created = [r for r in self.state.results if r.action == "created"]
        skipped = [r for r in self.state.results if r.action == "skipped"]

        if len(created) == 1:
            # Single record: inline link
            result = created[0]
            summary = await _format_record_summary(result)
            embed = discord.Embed(
                description=f"Created a {summary}.",
                color=discord.Color.green(),
            )
        elif created:
            # Multiple records: each with its own link
            lines = []
            for r in created:
                summary = await _format_record_summary(r)
                lines.append(f"• {summary}")
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
            embed = _create_status_embed("Cancelled.", variant="cancelled")
            await interaction.response.edit_message(embed=embed, view=WizardCompletionView(None))
        except Exception as e:
            logger.exception("discord_cancel_error", extra={"error": str(e)})
            await _send_error_response(interaction, "Failed to cancel.")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip this suggestion (multiple items only)."""
        try:
            self.state.record_result("skipped")

            if self.state.is_complete:
                embed, view = await self.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = await self.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.exception("discord_skip_error", extra={"error": str(e)})
            await _send_error_response(interaction, "Failed to skip.")

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to edit, then create on submit."""
        try:
            modal = SuggestionEditorModal(self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.exception("discord_edit_error", extra={"error": str(e)})
            await _send_error_response(interaction, "Failed to open editor.")

    @discord.ui.button(label="Create", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create with current description."""
        try:
            suggestion = self.state.current_suggestion
            if suggestion:
                # Set parent_record_id for child suggestions
                parent_record_id = self.state.get_parent_record_id_for_current()
                if parent_record_id is not None:
                    suggestion.parent_record_id = parent_record_id

                result = await create_record_with_media(
                    suggestion=suggestion,
                    author_id=self.state.get_author_id_for_current(),
                    author_id_map=self.state.author_id_map,
                    message_timestamp_map=self.state.message_timestamp_map,
                    message_attachments=self.state.message_attachments,
                )
                self.state.record_result(
                    "created", url=result.result.url, record_id=result.result.record_id
                )

            if self.state.is_complete:
                embed, view = await self.build_completion_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = await self.build_step_embed()
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.exception("discord_create_error", extra={"error": str(e)})
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

        # logger.exception() automatically includes the full traceback
        logger.exception(
            "discord_command_error",
            extra={
                "command": interaction.command.name if interaction.command else "unknown",
                "error": str(original),
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
            logger.exception("discord_setup_hook_error", extra={"error": str(e)})

    async def on_ready(self):
        """Called when the bot has connected to Discord."""
        logger.info(
            "discord_bot_connected",
            extra={
                "user": str(self.user),
                "user_id": self.user.id if self.user else None,
            },
        )

        # Warn about missing media upload configuration
        if not DJANGO_WEB_SERVICE_URL:
            logger.warning(
                "discord_config_missing",
                extra={"setting": "DJANGO_WEB_SERVICE_URL", "impact": "media_uploads_disabled"},
            )
        if not TRANSCODING_UPLOAD_TOKEN:
            logger.warning(
                "discord_config_missing",
                extra={"setting": "TRANSCODING_UPLOAD_TOKEN", "impact": "media_uploads_disabled"},
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
            logger.warning(
                "discord_interaction_already_acknowledged",
                extra={"interaction_id": interaction.id},
            )
            return

        # MUST defer immediately - Discord only gives 3 seconds to respond
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if this message has already been processed
            if await _is_message_processed(str(message.id)):
                embed = _create_status_embed(
                    "This message has already been saved to Flipfix.",
                    title="Already Processed",
                    variant="info",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Gather context around the clicked message
            context = await gather_context(message)

            # Count total messages including nested thread messages
            message_count = sum(1 + len(m.thread) for m in context.messages)
            logger.info(
                "discord_analyzing_messages",
                extra={"message_count": message_count, "target_id": message.id},
            )

            # Analyze with LLM
            result = await analyze_gathered_context(context)

            if result.is_error:
                assert result.error is not None  # Guaranteed by is_error check
                embed = _create_status_embed(
                    result.error,
                    title="Analysis Error",
                    variant="error",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            elif result.suggestions:
                logger.info(
                    "discord_suggestions_generated",
                    extra={"suggestion_count": len(result.suggestions)},
                )

                # Build attachment map from context messages
                message_attachments = _build_attachment_map(context.messages)

                view = SequentialWizardView(
                    suggestions=result.suggestions,
                    discord_user=DiscordUserInfo.from_interaction(interaction),
                    discord_message_id=message.id,
                    author_id_map=context.author_id_map,
                    message_timestamp_map=context.message_timestamp_map,
                    message_attachments=message_attachments,
                )
                embed = await view.build_step_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = _create_status_embed(
                    "No maintenance records were identified in these messages.\n\nTry selecting a message that discusses machine repairs, problems, or parts.",
                    title="No Records Found",
                    variant="info",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("discord_add_command_error", extra={"error": str(e)})
            embed = _create_status_embed(
                "Failed to analyze messages. Please try again.",
                title="Error",
                variant="error",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @staticmethod
    async def _get_guild_id() -> str:
        """Get guild ID from Constance config."""

        @sync_to_async
        def get_config():
            return config.DISCORD_GUILD_ID

        return await get_config()


def _format_record_type(record_type: RecordType) -> str:
    """Format record type for display."""
    type_labels = {
        RecordType.LOG_ENTRY: "Log Entry",
        RecordType.PROBLEM_REPORT: "Problem Report",
        RecordType.PART_REQUEST: "Part Request",
        RecordType.PART_REQUEST_UPDATE: "Part Request Update",
    }
    return type_labels.get(record_type, record_type.value.replace("_", " ").title())


def _get_parent_type_label(child_record_type: RecordType) -> str:
    """Get the parent record type label for a child record type.

    Log entries link to problem reports; part request updates link to part requests.
    """
    parent_labels = {
        RecordType.LOG_ENTRY: "Problem Report",
        RecordType.PART_REQUEST_UPDATE: "Part Request",
    }
    return parent_labels.get(child_record_type, "Record")


async def _get_machine_name(slug: str | None) -> str | None:
    """Look up machine display name by slug, falling back to the slug if not found."""
    if not slug:
        return None

    @sync_to_async
    def lookup():
        machine = MachineInstance.objects.filter(slug=slug).first()
        return machine.name if machine else slug

    return await lookup()


async def _format_record_summary(result: WizardResult, include_link: bool = True) -> str:
    """Format a wizard result for display in completion messages."""
    type_display = _format_record_type(result.suggestion.record_type)
    machine_name = await _get_machine_name(result.suggestion.slug)

    if machine_name:
        base = f"{type_display} on {machine_name}"
    else:
        base = type_display

    if include_link and result.url:
        return f"{base} — [View in Flipfix ➡️]({result.url})"
    return base


async def _is_message_processed(message_id: str) -> bool:
    """Check if a Discord message has already been processed."""
    return await sync_to_async(DiscordMessageMapping.is_processed)(message_id)


def _format_media_counts(attachments: list[discord.Attachment]) -> str | None:
    """Format attachment counts for footer display.

    Returns a string like "3 photos, 1 video" or None if no attachments.
    """
    if not attachments:
        return None

    photos = sum(1 for a in attachments if not _is_video(a.filename))
    videos = sum(1 for a in attachments if _is_video(a.filename))

    parts = []
    if photos:
        parts.append(f"{photos} photo" if photos == 1 else f"{photos} photos")
    if videos:
        parts.append(f"{videos} video" if videos == 1 else f"{videos} videos")

    return ", ".join(parts) if parts else None


def _build_attachment_map(
    context_messages: list[ContextMessage],
) -> dict[str, list[discord.Attachment]]:
    """Build a mapping of message IDs to their attachments.

    Includes attachments from thread messages nested under their parent.
    """
    attachment_map: dict[str, list[discord.Attachment]] = {}
    for msg in context_messages:
        if msg.attachments:
            attachment_map[msg.id] = msg.attachments
        for thread_msg in msg.thread:
            if thread_msg.attachments:
                attachment_map[thread_msg.id] = thread_msg.attachments

    if attachment_map:
        logger.info(
            "discord_attachment_map_built",
            extra={
                "message_count": len(attachment_map),
                "message_ids": list(attachment_map.keys()),
                "total_attachments": sum(len(a) for a in attachment_map.values()),
            },
        )
    else:
        logger.debug(
            "discord_attachment_map_empty", extra={"context_message_count": len(context_messages)}
        )

    return attachment_map


def _create_status_embed(
    description: str,
    *,
    title: str | None = None,
    variant: str = "info",
) -> discord.Embed:
    """Create a status embed with consistent styling.

    Variants: success (green), error (red), info (grey), cancelled (greyple)
    """
    color_map = {
        "success": discord.Color.green(),
        "error": discord.Color.red(),
        "info": discord.Color.light_grey(),
        "cancelled": discord.Color.greyple(),
    }
    embed = discord.Embed(
        description=description,
        color=color_map.get(variant, discord.Color.light_grey()),
    )
    if title:
        embed.title = title
    return embed


async def _send_error_response(interaction: discord.Interaction, message: str):
    """Send an error response, handling both deferred and non-deferred states."""
    embed = _create_status_embed(message, title="Error", variant="error")

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as e:
        logger.warning("discord_error_response_failed", extra={"error": str(e)})


def run_bot():
    """Run the Discord bot. Called from the management command."""
    if not config.DISCORD_BOT_ENABLED:
        logger.error("discord_bot_disabled")
        return

    token = config.DISCORD_BOT_TOKEN
    if not token:
        logger.error("discord_bot_token_not_configured")
        return

    bot = DiscordBot()

    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error("discord_bot_invalid_token")
    except Exception as e:
        logger.exception("discord_bot_error", extra={"error": str(e)})
