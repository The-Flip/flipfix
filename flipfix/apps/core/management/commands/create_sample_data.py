"""Run all sample data creators."""

from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create all sample data (dev/PR environments only, not prod)."

    def handle(self, *args: object, **options: object) -> None:
        # Safety check: never populate the real production/staging database.
        if not settings.ALLOW_SAMPLE_DATA:
            raise CommandError(
                "Sample data commands are disabled in this environment (production/staging)."
            )

        self.stdout.write(self.style.SUCCESS("Creating sample data..."))

        # Run individual sample data creators
        call_command("create_sample_accounts")
        call_command("create_sample_machines")
        call_command("import_machine_sign_copy")
        call_command("create_sample_logs_problems")
        call_command("create_sample_parts")
        call_command("create_sample_infinite_scrolling_data")

        self.stdout.write(self.style.SUCCESS("\nSample data creation complete."))
