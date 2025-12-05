"""Evaluate Discord message classifier against historical messages.

Runs the message parser against a CSV of Discord messages and outputs
classification results to a CSV for review in a spreadsheet.

Usage:
    python manage.py evaluate_classifier
    python manage.py evaluate_classifier --output results.csv
"""

import csv
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.discord.parsers import parse_message


class Command(BaseCommand):
    help = "Evaluate classifier against historical Discord messages"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            default="~/Downloads/discord_classification_results.csv",
            help="Output CSV file path (default: ~/Downloads/discord_classification_results.csv)",
        )
        parser.add_argument(
            "--input",
            "-i",
            default=None,
            help="Input CSV file path (default: fixtures/discord_workshop_messages.csv)",
        )

    def handle(self, *args, **options):
        fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
        input_path = options["input"] or fixtures_dir / "discord_workshop_messages.csv"
        output_path = Path(options["output"]).expanduser()

        # Load machines from fixture CSV
        self._load_machines(fixtures_dir / "machines.csv")

        # Process messages and write results
        results = self._classify_messages(input_path)
        self._write_results(output_path, results)

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(results)} classifications to {output_path}")
        )

    def _load_machines(self, machines_csv: Path):
        """Load machines from CSV fixture."""
        # Clear the machine cache
        cache.delete("machines_for_matching")

        with open(machines_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                model, _ = MachineModel.objects.get_or_create(
                    name=row["model_name"],
                    defaults={
                        "manufacturer": row["manufacturer"],
                        "year": int(row["year"]) if row["year"] else None,
                    },
                )
                name_override = (
                    row["display_name"] if row["display_name"] != row["model_name"] else ""
                )
                MachineInstance.objects.get_or_create(
                    slug=row["slug"],
                    defaults={
                        "model": model,
                        "name_override": name_override,
                    },
                )

    def _classify_messages(self, messages_csv: Path) -> list[dict]:
        """Run classifier on all messages and return results."""
        results = []

        with open(messages_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                content = row.get("content", "")
                if not content:
                    continue

                result = parse_message(content)

                classification = result.record_type.value if result.record_type else "ignore"
                machine = result.machine.display_name if result.machine else ""

                results.append(
                    {
                        "classification": classification,
                        "machine": machine,
                        "reason": result.reason,
                        "author": row.get("authorName", ""),
                        "date": row.get("date", ""),
                        "content": content,
                    }
                )

        return results

    def _write_results(self, output_path: str, results: list[dict]):
        """Write classification results to CSV."""
        fieldnames = ["classification", "machine", "reason", "author", "date", "content"]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
