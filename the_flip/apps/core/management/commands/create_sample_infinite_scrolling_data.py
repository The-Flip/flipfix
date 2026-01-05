"""Generate procedural data for infinite scroll testing."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

# NATO phonetic alphabet for fake reporter names (searchable in free-text fields)
NATO_ALPHABET = [
    "Alpha",
    "Bravo",
    "Charlie",
    "Delta",
    "Echo",
    "Foxtrot",
    "Golf",
    "Hotel",
    "India",
    "Juliet",
    "Kilo",
    "Lima",
    "Mike",
    "November",
    "Oscar",
    "Papa",
    "Quebec",
    "Romeo",
    "Sierra",
    "Tango",
    "Uniform",
    "Victor",
    "Whiskey",
    "X-ray",
    "Yankee",
    "Zulu",
]


class Command(BaseCommand):
    help = (
        "Generate procedural data for infinite scroll testing (dev/PR environments only, not prod)."
    )

    # Target machine for infinite scroll testing
    TARGET_MACHINE_SHORT_NAME = "Eight Ball 2"
    RECORDS_PER_TYPE = 25

    def handle(self, *args: object, **options: object) -> None:
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
            )

        self.stdout.write(self.style.SUCCESS("\nGenerating records to test infinite scrolling..."))

        # Find target machine
        machine = MachineInstance.objects.filter(short_name=self.TARGET_MACHINE_SHORT_NAME).first()
        if not machine:
            raise CommandError(
                f"Target machine '{self.TARGET_MACHINE_SHORT_NAME}' not found. "
                "Run create_sample_machines first."
            )

        # Base time: 200 minutes ago (ensures no future dates)
        base_time = timezone.now() - timedelta(minutes=200)

        # Generate problem reports
        first_problem = None
        for i in range(self.RECORDS_PER_TYPE):
            occurred_at = base_time + timedelta(minutes=i * 8)  # T+0, T+8, T+16...
            random_word = secrets.token_hex(3)[:5]
            fake_name = NATO_ALPHABET[i % len(NATO_ALPHABET)]

            problem = ProblemReport.objects.create(
                machine=machine,
                description=f"Test problem #{i + 1} [{random_word}]",
                status=ProblemReport.Status.OPEN,
                problem_type=ProblemReport.ProblemType.OTHER,
                reported_by_name=fake_name,
                occurred_at=occurred_at,
            )
            if i == 0:
                first_problem = problem

        # Generate part requests
        first_part_request = None
        for i in range(self.RECORDS_PER_TYPE):
            occurred_at = base_time + timedelta(minutes=i * 8 + 2)  # T+2, T+10, T+18...
            random_word = secrets.token_hex(3)[:5]
            fake_name = NATO_ALPHABET[i % len(NATO_ALPHABET)]

            part_request = PartRequest.objects.create(
                machine=machine,
                text=f"Test part request #{i + 1} [{random_word}]",
                status=PartRequest.Status.REQUESTED,
                requested_by_name=fake_name,
                occurred_at=occurred_at,
            )
            if i == 0:
                first_part_request = part_request

        # Generate log entries (attached to first problem report)
        if first_problem:
            for i in range(self.RECORDS_PER_TYPE):
                occurred_at = base_time + timedelta(minutes=i * 8 + 4)  # T+4, T+12, T+20...
                random_word = secrets.token_hex(3)[:5]
                fake_name = NATO_ALPHABET[i % len(NATO_ALPHABET)]

                LogEntry.objects.create(
                    machine=machine,
                    problem_report=first_problem,
                    text=f"Test log entry #{i + 1} [{random_word}]",
                    maintainer_names=fake_name,
                    occurred_at=occurred_at,
                )

        # Generate part request updates (attached to first part request)
        if first_part_request:
            for i in range(self.RECORDS_PER_TYPE):
                occurred_at = base_time + timedelta(minutes=i * 8 + 6)  # T+6, T+14, T+22...
                random_word = secrets.token_hex(3)[:5]
                fake_name = NATO_ALPHABET[i % len(NATO_ALPHABET)]

                PartRequestUpdate.objects.create(
                    part_request=first_part_request,
                    text=f"Test update #{i + 1} [{random_word}]",
                    posted_by_name=fake_name,
                    occurred_at=occurred_at,
                )

        n = self.RECORDS_PER_TYPE
        display_name = machine.short_name or machine.name
        self.stdout.write(
            self.style.SUCCESS(
                f"Generated {n} problem reports, {n} log entries, "
                f"{n} part requests and {n} part request updates for {display_name}"
            )
        )
