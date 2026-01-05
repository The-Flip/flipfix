"""Create sample log entries and problem reports."""

from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.models import (
    LogEntry,
    LogEntryMedia,
    ProblemReport,
    ProblemReportMedia,
)


class Command(BaseCommand):
    help = "Create sample log entries and problem reports from docs/sample_data/logs_problems.json (dev/PR only)"

    data_path = Path("docs/sample_data/records/logs_problems.json")
    media_path = Path("docs/sample_data/media")

    def __init__(self):
        super().__init__()
        self.machine_name_mapping = {}
        self.maintainer_name_mapping = {
            self.normalize_name("caleb"): "junkybrassmonkey",
        }

    def handle(self, *args, **options):
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
            )

        # Safety check: empty database only
        if ProblemReport.objects.exists() or LogEntry.objects.exists():
            raise CommandError(
                "Database already contains maintenance records. "
                "This command only runs on empty databases."
            )

        if not self.data_path.exists():
            raise CommandError(f"Data file not found: {self.data_path}")

        with self.data_path.open() as fh:
            data = json.load(fh)

        self.stdout.write(
            self.style.SUCCESS("\nCreating sample problem reports and log entries...")
        )

        # Import problem reports (with nested log entries)
        problem_count, attached_log_count = self.import_problems(data.get("problem_reports", []))

        # Import standalone log entries
        standalone_log_count = self.import_log_entries(data.get("log_entries", []))

        total_logs = attached_log_count + standalone_log_count
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {problem_count} problem reports and {total_logs} log entries."
            )
        )

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def normalize_name(value: str) -> str:
        if not value:
            return ""
        normalized = re.sub(r"[^\w\s]", "", value.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def find_machine(self, name: str) -> MachineInstance | None:
        target = self.normalize_name(name)
        if not target:
            return None
        machines = MachineInstance.objects.all()
        for machine in machines:
            if self.normalize_name(machine.name) == target:
                return machine
            if machine.short_name and self.normalize_name(machine.short_name) == target:
                return machine
        mapped_name = self.machine_name_mapping.get(target)
        if mapped_name:
            mapped_target = self.normalize_name(mapped_name)
            for machine in machines:
                if self.normalize_name(machine.name) == mapped_target:
                    return machine
        return MachineInstance.objects.filter(slug=name).first()

    def find_maintainer(self, name: str) -> Maintainer | None:
        target = self.normalize_name(name)
        if not target:
            return None
        if target in self.maintainer_name_mapping:
            target = self.normalize_name(self.maintainer_name_mapping[target])
        for maintainer in Maintainer.objects.select_related("user"):
            username = self.normalize_name(maintainer.user.username)
            first = self.normalize_name(maintainer.user.first_name or "")
            last = self.normalize_name(maintainer.user.last_name or "")
            full = self.normalize_name(
                f"{maintainer.user.first_name} {maintainer.user.last_name}".strip()
            )
            if target in {username, first, last, full}:
                return maintainer
        return None

    @staticmethod
    def parse_iso_datetime(raw: str) -> datetime:
        if not raw:
            return timezone.now()
        try:
            # Parse ISO format datetime
            dt = datetime.fromisoformat(raw)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            return timezone.now()

    def _create_media_attachments(
        self,
        media_filenames: list[str],
        parent: ProblemReport | LogEntry,
    ) -> int:
        """Create media attachments for a problem report or log entry.

        Returns the number of media files successfully attached.
        Raises CommandError if any media file is not found.
        """
        if not media_filenames:
            return 0

        created = 0
        for filename in media_filenames:
            file_path = self.media_path / filename
            if not file_path.exists():
                raise CommandError(f"Media file not found: {file_path}")

            # Determine content type from extension
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

            # Read file and create SimpleUploadedFile
            with file_path.open("rb") as f:
                content = f.read()

            uploaded_file = SimpleUploadedFile(
                name=filename,
                content=content,
                content_type=content_type,
            )

            # Create the appropriate media record
            if isinstance(parent, ProblemReport):
                ProblemReportMedia.objects.create(
                    problem_report=parent,
                    media_type=ProblemReportMedia.MediaType.PHOTO,
                    file=uploaded_file,
                )
            else:
                LogEntryMedia.objects.create(
                    log_entry=parent,
                    media_type=LogEntryMedia.MediaType.PHOTO,
                    file=uploaded_file,
                )

            created += 1

        return created

    # ---- importers -------------------------------------------------------
    def import_problems(self, problems_data: list) -> tuple[int, int]:
        """Import problem reports with nested logs. Returns (problem_count, log_count)."""
        created_problems = 0
        created_logs = 0
        problem_summaries: list[str] = []

        for problem_entry in problems_data:
            machine_name = problem_entry.get("machine", "").strip()
            description = problem_entry.get("description", "").strip()
            if not machine_name or not description:
                self.stdout.write(
                    self.style.WARNING("  Skipping problem missing machine or description.")
                )
                continue

            machine = self.find_machine(machine_name)
            if not machine:
                raise CommandError(
                    f"Machine not found: '{machine_name}'. "
                    "Run create_sample_machines first or fix logs_problems.json."
                )

            # Find reporter
            reporter_name = problem_entry.get("reported_by", "").strip()
            reporter = self.find_maintainer(reporter_name) if reporter_name else None

            # Determine status
            status_str = problem_entry.get("status", "open").lower()
            status = (
                ProblemReport.Status.CLOSED if status_str == "closed" else ProblemReport.Status.OPEN
            )

            occurred_at = self.parse_iso_datetime(problem_entry.get("occurred_at", ""))

            problem_report = ProblemReport.objects.create(
                machine=machine,
                description=description,
                status=status,
                problem_type=ProblemReport.ProblemType.OTHER,
                reported_by_user=reporter.user if reporter else None,
                occurred_at=occurred_at,
            )
            created_problems += 1

            # Attach media if any
            media_filenames = problem_entry.get("media", [])
            self._create_media_attachments(media_filenames, problem_report)

            # Create nested log entries if any
            log_count = 0
            for log_entry_data in problem_entry.get("log_entries", []):
                log_created = self._create_log_entry(
                    log_entry_data, machine, problem_report=problem_report
                )
                if log_created:
                    created_logs += 1
                    log_count += 1

            # Build summary for this problem
            display_name = machine.short_name or machine.name
            if log_count == 0:
                problem_summaries.append(display_name)
            elif log_count == 1:
                problem_summaries.append(f"{display_name} (1 log)")
            else:
                problem_summaries.append(f"{display_name} ({log_count} logs)")

        if problem_summaries:
            self.stdout.write(f"  Problem reports: {', '.join(problem_summaries)}")

        return created_problems, created_logs

    def import_log_entries(self, logs_data: list) -> int:
        """Import standalone log entries. Returns count of logs created."""
        # Group logs by machine for summary
        machine_log_counts: dict[str, int] = {}

        for log_entry_data in logs_data:
            machine_name = log_entry_data.get("machine", "").strip()
            if not machine_name:
                self.stdout.write(self.style.WARNING("  Skipping log entry missing machine."))
                continue

            machine = self.find_machine(machine_name)
            if not machine:
                raise CommandError(
                    f"Machine not found: '{machine_name}'. "
                    "Run create_sample_machines first or fix logs_problems.json."
                )

            if self._create_log_entry(log_entry_data, machine, problem_report=None):
                display_name = machine.short_name or machine.name
                machine_log_counts[display_name] = machine_log_counts.get(display_name, 0) + 1

        # Build summary
        if machine_log_counts:
            summaries = []
            for name, count in machine_log_counts.items():
                if count == 1:
                    summaries.append(name)
                else:
                    summaries.append(f"{name} ({count} logs)")
            self.stdout.write(f"  Standalone log entries: {', '.join(summaries)}")

        return sum(machine_log_counts.values())

    def _create_log_entry(
        self,
        data: dict,
        machine: MachineInstance,
        *,
        problem_report: ProblemReport | None,
    ) -> LogEntry | None:
        """Create a single log entry from JSON data."""
        text = data.get("text", "").strip()
        if not text:
            self.stdout.write(self.style.WARNING("Skipping log entry missing text."))
            return None

        occurred_at = self.parse_iso_datetime(data.get("occurred_at", ""))
        maintainer_names = data.get("maintainers", [])

        matched = []
        unmatched = []
        for name in maintainer_names:
            maintainer = self.find_maintainer(name)
            if maintainer:
                matched.append(maintainer)
            else:
                unmatched.append(name)

        entry = LogEntry.objects.create(
            machine=machine,
            problem_report=problem_report,
            text=text,
            maintainer_names=", ".join(unmatched),
            occurred_at=occurred_at,
        )
        if matched:
            entry.maintainers.set(matched)

        # Attach media if any
        media_filenames = data.get("media", [])
        self._create_media_attachments(media_filenames, entry)

        return entry
