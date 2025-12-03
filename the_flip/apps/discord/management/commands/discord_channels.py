"""Management command to view and manage Discord channels."""

from django.core.management.base import BaseCommand

from the_flip.apps.discord.models import DiscordChannel


class Command(BaseCommand):
    help = "View configured Discord channels. Bot auto-refreshes every 5 minutes."

    def handle(self, *args, **options):
        channels = DiscordChannel.objects.all()

        if not channels.exists():
            self.stdout.write(self.style.WARNING("No Discord channels configured."))
            self.stdout.write("Add channels in Django admin: /admin/discord/discordchannel/")
            return

        self.stdout.write(self.style.SUCCESS("Configured Discord channels:"))
        for channel in channels:
            status = (
                self.style.SUCCESS("enabled")
                if channel.is_enabled
                else self.style.ERROR("disabled")
            )
            self.stdout.write(f"  • {channel.name} ({channel.channel_id}) - {status}")

        self.stdout.write("")
        self.stdout.write("Note: The bot automatically refreshes its channel list every 5 minutes.")
        self.stdout.write("To force an immediate refresh, restart the bot service.")
