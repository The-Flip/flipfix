"""Shared types for Discord bot integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscordUserInfo:
    """Discord user information for record creation.

    Groups the three pieces of Discord user identity that travel together
    when creating records from Discord interactions.
    """

    user_id: str
    username: str | None = None
    display_name: str | None = None

    @classmethod
    def from_interaction(cls, interaction) -> DiscordUserInfo:
        """Create from a Discord interaction.

        Args:
            interaction: A discord.Interaction object
        """
        return cls(
            user_id=str(interaction.user.id),
            username=interaction.user.name,
            display_name=interaction.user.display_name,
        )

    @classmethod
    def from_message(cls, message) -> DiscordUserInfo:
        """Create from a Discord message.

        Args:
            message: A discord.Message object
        """
        return cls(
            user_id=str(message.author.id),
            username=message.author.name,
            display_name=message.author.display_name,
        )
