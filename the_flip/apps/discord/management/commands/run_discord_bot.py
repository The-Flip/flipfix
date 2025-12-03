"""Management command to run the Discord bot."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the Discord bot for processing maintenance messages"

    def handle(self, *args, **options):
        self.stdout.write("Starting Discord bot...")

        from the_flip.apps.discord.bot import run_bot

        run_bot()
