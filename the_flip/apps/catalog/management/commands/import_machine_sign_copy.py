"""Import museum sign data from Machine Sign Copy CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from the_flip.apps.catalog.models import MachineModel


class Command(BaseCommand):
    help = "Import museum sign data from Machine Sign Copy CSV into existing machines"

    csv_path = Path("docs/sample_data/Machine Sign Copy v0.5.csv")

    def handle(self, *args: object, **options: object) -> None:
        if not self.csv_path.exists():
            raise CommandError(f"CSV file not found: {self.csv_path}")

        self.stdout.write(
            self.style.SUCCESS(f"\nImporting machine sign copy from {self.csv_path.name}...")
        )

        with self.csv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            updated_count = 0
            skipped_count = 0

            for row in reader:
                ipdb_id = self._parse_ipdb_id(row.get("IPDBid", ""))
                if ipdb_id is None:
                    # Skip rows without valid IPDB ID
                    continue

                try:
                    model = MachineModel.objects.get(ipdb_id=ipdb_id)
                except MachineModel.DoesNotExist:
                    title = row.get("Title", "").strip()
                    self.stdout.write(
                        self.style.WARNING(f"  No machine found for IPDB ID {ipdb_id} ({title})")
                    )
                    skipped_count += 1
                    continue

                updated_fields = self._update_model(model, row)
                ownership_updated = self._update_instance_ownership(model, row)
                if ownership_updated:
                    updated_fields.append("ownership_credit")

                # Get display name (short_name if available)
                instance = model.instances.order_by("id").first()
                display_name = (
                    instance.short_name if instance and instance.short_name else model.name
                )

                if updated_fields:
                    self.stdout.write(f"  Updated {display_name}: {', '.join(updated_fields)}")
                updated_count += 1

            self.stdout.write(
                self.style.SUCCESS(f"Imported machine sign copy for {updated_count} machines.")
            )

    def _parse_ipdb_id(self, value: str) -> int | None:
        """Parse IPDB ID from string, returning None if invalid."""
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _update_model(self, model: MachineModel, row: dict) -> list[str]:
        """Update MachineModel fields from CSV row. Returns list of updated field names."""
        updated_fields = []

        # Direct field mappings
        new_educational_text = row.get("MainText", "").strip()
        if new_educational_text:
            model.educational_text = new_educational_text
            updated_fields.append("educational_text")

        new_production_quantity = row.get("Produced", "").strip() or None
        if new_production_quantity:
            model.production_quantity = new_production_quantity
            updated_fields.append("production_quantity")

        new_factory_address = row.get("Address", "").strip()
        if new_factory_address:
            model.factory_address = new_factory_address
            updated_fields.append("factory_address")

        new_illustration_filename = row.get("Illustration", "").strip()
        if new_illustration_filename:
            model.illustration_filename = new_illustration_filename
            updated_fields.append("illustration_filename")

        new_sources_notes = row.get("Sources/Notes", "").strip()
        if new_sources_notes:
            model.sources_notes = new_sources_notes
            updated_fields.append("sources_notes")

        # Parse dynamic Heading/Info columns for credits
        credit_fields = self._parse_credits(model, row)
        updated_fields.extend(credit_fields)

        model.save()
        return updated_fields

    def _parse_credits(self, model: MachineModel, row: dict) -> list[str]:
        """Parse Heading1/Info1, Heading2/Info2, Heading3/Info3 for credit fields.

        Returns list of updated credit field names.
        """
        updated_fields = []

        # Clear existing credit fields before parsing
        model.design_credit = ""
        model.concept_and_design_credit = ""
        model.art_credit = ""
        model.sound_credit = ""

        for heading_col, info_col in [
            ("Heading1", "Info1"),
            ("Heading2", "Info2"),
            ("Heading3", "Info3"),
        ]:
            heading = row.get(heading_col, "").strip().lower()
            info = row.get(info_col, "").strip()

            if not heading or not info:
                continue

            if heading == "design by":
                model.design_credit = info
                updated_fields.append("design_credit")
            elif heading == "concept and design by":
                model.concept_and_design_credit = info
                updated_fields.append("concept_and_design_credit")
            elif heading == "art by":
                model.art_credit = info
                updated_fields.append("art_credit")
            elif heading in ("sound by:", "sound by"):
                model.sound_credit = info
                updated_fields.append("sound_credit")

        return updated_fields

    def _update_instance_ownership(self, model: MachineModel, row: dict) -> bool:
        """Update ownership_credit on the first instance (by lowest ID).

        Returns True if ownership was updated, False otherwise.
        """
        ownership = row.get("Ownership", "").strip()
        if not ownership:
            return False

        # Get first instance by ID for this model
        instance = model.instances.order_by("id").first()
        if instance is None:
            raise CommandError(
                f"Machine model '{model.name}' has no instances. Run create_sample_machines first."
            )

        instance.ownership_credit = ownership
        instance.save()
        return True
