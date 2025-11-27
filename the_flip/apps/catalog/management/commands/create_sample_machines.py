"""Create sample machine models and instances from legacy JSON data."""

import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from the_flip.apps.catalog.models import MachineInstance, MachineModel


class Command(BaseCommand):
    help = "Create sample machine data from docs/legacy_data/machines.json (dev/PR only)"

    data_path = Path("docs/legacy_data/machines.json")

    def handle(self, *args, **options):
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
            payload = json.load(fh)

        models_map = {}
        for data in payload.get("models", []):
            model_data = data.copy()
            pinside = model_data.get("pinside_rating")
            if pinside is not None:
                model_data["pinside_rating"] = Decimal(str(pinside))
            model = MachineModel.objects.create(
                name=model_data.pop("name"),
                **model_data,
            )
            models_map[model.name] = model
            self.stdout.write(f"Created model: {model.name}")

        for data in payload.get("instances", []):
            model_name = data.pop("model_name")
            model = models_map.get(model_name)
            if not model:
                self.stdout.write(self.style.ERROR(f"Skipping unknown model {model_name}"))
                continue
            instance_data = data.copy()
            instance = MachineInstance.objects.create(
                model=model,
                **instance_data,
            )
            self.stdout.write(f"Created instance: {instance.display_name}")

        self.stdout.write(self.style.SUCCESS("Sample machine data created."))
