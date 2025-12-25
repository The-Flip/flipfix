"""Backfill NULL/empty name values with model name (with counter for uniqueness)."""

from django.db import migrations
from django.db.models import Q
from django.db.models.functions import Trim


def backfill_name(apps, schema_editor):
    """Populate NULL or empty name values with model name."""
    MachineInstance = apps.get_model("catalog", "MachineInstance")
    MachineModel = apps.get_model("catalog", "MachineModel")

    # Find NULL, empty, or whitespace-only values
    # Using Trim annotation instead of regex for SQLite/Postgres portability
    empty_names = (
        MachineInstance.objects.annotate(trimmed=Trim("name"))
        .filter(Q(name__isnull=True) | Q(trimmed=""))
        .select_related("model")
    )

    for instance in empty_names:
        model_name = instance.model.name
        counter = 1
        candidate = model_name
        while MachineInstance.objects.filter(name=candidate).exists():
            counter += 1
            candidate = f"{model_name} #{counter}"
        instance.name = candidate
        instance.save(update_fields=["name"])

    # Also backfill HistoricalMachineInstance - use the model name from the
    # historical record's model_id FK. Historical records don't need unique
    # names, just non-NULL values that reflect what the name would have been.
    HistoricalMachineInstance = apps.get_model("catalog", "HistoricalMachineInstance")
    empty_historical = (
        HistoricalMachineInstance.objects.annotate(trimmed=Trim("name"))
        .filter(Q(name__isnull=True) | Q(trimmed=""))
    )

    for hist in empty_historical:
        if hist.model_id:
            try:
                model = MachineModel.objects.get(pk=hist.model_id)
                hist.name = model.name
            except MachineModel.DoesNotExist:
                # Model was deleted - use a descriptive fallback
                hist.name = f"(deleted model #{hist.model_id})"
        else:
            hist.name = "(no model)"
        hist.save(update_fields=["name"])


def reverse_backfill(apps, schema_editor):
    """No-op reverse - we can't know which names were auto-generated."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_rename_name_override_to_name"),
    ]

    operations = [
        migrations.RunPython(backfill_name, reverse_backfill),
    ]
