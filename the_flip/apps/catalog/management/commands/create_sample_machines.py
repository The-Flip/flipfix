"""Create sample machine models and instances."""

import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from the_flip.apps.catalog.models import Location, MachineInstance, MachineModel


class Command(BaseCommand):
    help = "Create sample machine data from docs/sample_data/machines.json (dev/PR environments only, not prod)"

    data_path = Path("docs/sample_data/records/machines.json")

    def handle(self, *args: object, **options: object) -> None:
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
            )

        # Safety check: empty database only
        if MachineModel.objects.exists() or MachineInstance.objects.exists():
            raise CommandError(
                "Database already contains machine data. This command only runs on empty databases."
            )

        if not self.data_path.exists():
            raise CommandError(f"Data file not found: {self.data_path}")

        with self.data_path.open() as fh:
            models_data = json.load(fh)

        self.stdout.write(self.style.SUCCESS("\nCreating sample machines..."))

        # Cache locations to avoid repeated lookups
        locations_map: dict[str, Location | None] = {"": None}
        instance_names: list[str] = []

        for model_entry in models_data:
            # Extract instances before creating model (they're nested now)
            instances_data = model_entry.pop("instances", None)

            # Convert pinside_rating to Decimal if present
            pinside = model_entry.get("pinside_rating")
            if pinside is not None:
                model_entry["pinside_rating"] = Decimal(str(pinside))

            # Create the model
            model = MachineModel.objects.create(
                name=model_entry.pop("name"),
                **model_entry,
            )

            # Create instances - if none specified, create one with the model name
            if instances_data is None:
                instances_data = [{}]  # Will default to model name

            for instance_entry in instances_data:
                instance_data = instance_entry.copy()

                # Convert location string to Location instance (case-insensitive lookup)
                location_name = instance_data.pop("location", "")
                if location_name and location_name not in locations_map:
                    # Case-insensitive lookup, then create if not found
                    location = Location.objects.filter(name__iexact=location_name).first()
                    if not location:
                        location = Location.objects.create(name=location_name.title())
                    locations_map[location_name] = location
                instance_data["location"] = locations_map.get(location_name)

                # Default name to model name if not specified
                instance_data.setdefault("name", model.name)

                # Create the instance
                instance = MachineInstance(model=model, **instance_data)
                instance._skip_auto_log = True  # type: ignore[attr-defined]
                instance.save()

                # Use short_name if available, otherwise name
                display_name = instance.short_name or instance.name
                instance_names.append(display_name)

        # Summary output
        self.stdout.write(f"  {', '.join(instance_names)}")
        self.stdout.write(self.style.SUCCESS(f"Created {len(instance_names)} sample machines."))
