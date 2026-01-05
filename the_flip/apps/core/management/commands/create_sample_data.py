"""Run all sample data creators."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Create all sample data (dev/PR environments only, not prod)."

    def handle(self, *args, **options):
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
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
