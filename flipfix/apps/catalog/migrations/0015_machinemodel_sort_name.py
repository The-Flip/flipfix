"""Add sort_name field to MachineModel for article-aware alphabetical sorting."""

import re

from django.db import migrations, models


def backfill_sort_name(apps, schema_editor):
    """Populate sort_name for all existing MachineModel rows."""
    MachineModel = apps.get_model("catalog", "MachineModel")
    pattern = re.compile(r"^(The|A|An)\s+", re.IGNORECASE)
    batch = []
    for obj in MachineModel.objects.only("name").iterator(chunk_size=500):
        stripped = pattern.sub("", obj.name)
        obj.sort_name = stripped if stripped else obj.name
        batch.append(obj)
    if batch:
        MachineModel.objects.bulk_update(batch, ["sort_name"])


def reverse_backfill(apps, schema_editor):
    """Clear sort_name (field will be dropped by reverse AddField)."""


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0014_name_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="machinemodel",
            name="sort_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Name with leading articles stripped, for alphabetical sorting",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="historicalmachinemodel",
            name="sort_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Name with leading articles stripped, for alphabetical sorting",
                max_length=200,
            ),
        ),
        migrations.RunPython(backfill_sort_name, reverse_backfill),
        migrations.AlterModelOptions(
            name="machinemodel",
            options={"ordering": ["sort_name"]},
        ),
        migrations.AlterModelOptions(
            name="machineinstance",
            options={"ordering": ["model__sort_name", "serial_number"]},
        ),
    ]
