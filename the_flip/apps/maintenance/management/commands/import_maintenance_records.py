"""Import legacy maintenance CSV data into the new maintenance models."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


class Command(BaseCommand):
    help = "Import legacy problem reports and log entries"

    problems_filename = "Maintenance - Problems.csv"
    logs_filename = "Maintenance - Log entries.csv"

    def __init__(self):
        super().__init__()
        self.machine_name_mapping = {
            self.normalize_name("RotoPool"): "Roto Pool",
            self.normalize_name("Addams Family"): "The Addams Family",
            self.normalize_name("The Getaway: High Speed 2"): "The Getaway: High Speed II",
            self.normalize_name("Hulk"): "The Incredible Hulk",
        }
        self.maintainer_name_mapping = {
            self.normalize_name("Wlliam"): "William",
        }

    def handle(self, *args, **options):
        base_path = Path(settings.BASE_DIR) / "docs" / "legacy_data"
        problems_path = base_path / self.problems_filename
        logs_path = base_path / self.logs_filename

        if problems_path.exists():
            self.import_problems(problems_path)
        else:
            self.stdout.write(self.style.ERROR(f"Problems CSV not found: {problems_path}"))

        if logs_path.exists():
            self.import_log_entries(logs_path)
        else:
            self.stdout.write(self.style.ERROR(f"Log entries CSV not found: {logs_path}"))

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
            if self.normalize_name(machine.display_name) == target:
                return machine
        mapped_name = self.machine_name_mapping.get(target)
        if mapped_name:
            mapped_target = self.normalize_name(mapped_name)
            for machine in machines:
                if self.normalize_name(machine.display_name) == mapped_target:
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
    def parse_date(raw: str) -> datetime:
        if not raw:
            return timezone.now()
        formats = [
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M %p",
            "%m/%d/%Y, %I:%M %p",
            "%m/%d/%y, %I:%M %p",
            "%m/%d/%Y",
            "%m/%d/%y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except ValueError:
                continue
        return timezone.now()

    # ---- importers -------------------------------------------------------
    def import_problems(self, csv_path: Path) -> None:
        self.stdout.write(self.style.SUCCESS("\nImporting problem reports..."))
        created = 0
        errors = 0

        with csv_path.open() as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                machine_name = (row.get("Game") or "").strip()
                description = (row.get("Problem") or "").strip()
                if not machine_name or not description:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING("Skipping row missing machine or problem text.")
                    )
                    continue

                machine = self.find_machine(machine_name)
                if not machine:
                    errors += 1
                    self.stdout.write(
                        self.style.ERROR(f"Machine not found for problem report: {machine_name}")
                    )
                    continue

                maintainer_name = (row.get("Maintainer") or "").strip()
                maintainer = self.find_maintainer(maintainer_name) if maintainer_name else None
                status = (
                    ProblemReport.STATUS_CLOSED
                    if (row.get("Checked / Unchecked") or "").lower() == "checked"
                    else ProblemReport.STATUS_OPEN
                )
                created_at = self.parse_date(row.get("Timestamp") or "")

                report = ProblemReport.objects.create(
                    machine=machine,
                    description=description,
                    status=status,
                    problem_type=ProblemReport.PROBLEM_OTHER,
                    reported_by_user=maintainer.user if maintainer else None,
                )
                ProblemReport.objects.filter(pk=report.pk).update(created_at=created_at)
                created += 1
                self.stdout.write(f"• Problem report added for {machine.display_name}")

        self.stdout.write(
            self.style.SUCCESS(f"Problems import complete. Created {created}, errors {errors}.")
        )

    def import_log_entries(self, csv_path: Path) -> None:
        self.stdout.write(self.style.SUCCESS("\nImporting log entries..."))
        created = 0
        errors = 0

        with csv_path.open() as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                machine_name = (row.get("Machine") or "").strip()
                notes = (row.get("Notes") or "").strip()
                if not machine_name or not notes:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING("Skipping log entry missing machine or notes.")
                    )
                    continue

                machine = self.find_machine(machine_name)
                if not machine:
                    errors += 1
                    self.stdout.write(
                        self.style.ERROR(f"Machine not found for log entry: {machine_name}")
                    )
                    continue

                date = self.parse_date(row.get("Date") or "")
                maintainer_field = (row.get("Maintainers") or "").strip()
                maintainer_names = self.split_maintainer_names(maintainer_field)

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
                    text=notes,
                    maintainer_names=", ".join(unmatched),
                )
                if matched:
                    entry.maintainers.set(matched)
                LogEntry.objects.filter(pk=entry.pk).update(created_at=date)
                created += 1
                self.stdout.write(f"• Log entry added for {machine.display_name}")

        self.stdout.write(
            self.style.SUCCESS(f"Log import complete. Created {created}, errors {errors}.")
        )

    @staticmethod
    def split_maintainer_names(raw: str) -> list[str]:
        if not raw:
            return []
        names = []
        parts = raw.split(",")
        for part in parts:
            subparts = part.split(" and ")
            for name in subparts:
                cleaned = name.strip()
                if cleaned:
                    names.append(cleaned)
        return names
