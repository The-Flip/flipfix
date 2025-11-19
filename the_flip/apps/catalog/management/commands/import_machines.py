"""Import machine models and instances from legacy JSON data."""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from the_flip.apps.catalog.models import MachineInstance, MachineModel


class Command(BaseCommand):
    help = "Import machine models and instances from docs/legacy_data/machines.json"

    data_path = Path("docs/legacy_data/machines.json")

    def handle(self, *args, **options):
        if not self.data_path.exists():
            raise CommandError(f"Data file not found: {self.data_path}")

        MachineInstance.objects.all().delete()
        MachineModel.objects.all().delete()
        self.stdout.write(self.style.WARNING("Cleared existing catalog data."))

        with self.data_path.open() as fh:
            payload = json.load(fh)

        models_map = {}
        for data in payload.get("models", []):
            model_data = data.copy()
            pinside = model_data.get("pinside_rating")
            if pinside is not None:
                model_data["pinside_rating"] = Decimal(str(pinside))
            model, created = MachineModel.objects.update_or_create(
                name=model_data.pop("name"),
                defaults=model_data,
            )
            models_map[model.name] = model
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} model: {model.name}")

        for data in payload.get("instances", []):
            model_name = data.pop("model_name")
            model = models_map.get(model_name)
            if not model:
                self.stdout.write(self.style.ERROR(f"Skipping unknown model {model_name}"))
                continue
            instance_data = data.copy()
            serial_number = instance_data.get("serial_number", "")
            instance, created = MachineInstance.objects.update_or_create(
                model=model,
                serial_number=serial_number,
                defaults=instance_data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} instance: {instance.display_name}")

        self.stdout.write(self.style.SUCCESS("Import complete."))
