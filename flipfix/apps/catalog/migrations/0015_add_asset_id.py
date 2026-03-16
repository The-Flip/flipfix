"""Add asset_id field to MachineInstance.

Three-step migration:
1. Add field as non-unique with blank default
2. Backfill existing machines (ordered by created_at)
3. Make field unique
"""

from django.db import migrations, models


def backfill_asset_ids(apps, schema_editor):
    """Assign M0001, M0002, ... to existing machines ordered by created_at."""
    MachineInstance = apps.get_model("catalog", "MachineInstance")
    for index, machine in enumerate(
        MachineInstance.objects.order_by("created_at", "id"), start=1
    ):
        machine.asset_id = f"M{index:04d}"
        machine.save(update_fields=["asset_id"])


def reverse_backfill(apps, schema_editor):
    """Clear all asset_ids (field is about to be removed anyway)."""
    MachineInstance = apps.get_model("catalog", "MachineInstance")
    MachineInstance.objects.all().update(asset_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_name_not_null"),
    ]

    operations = [
        # Step 1: Add field (non-unique, allows blank)
        migrations.AddField(
            model_name="machineinstance",
            name="asset_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Unique asset identifier (e.g., M0001). Auto-generated.",
                max_length=10,
                verbose_name="Asset ID",
            ),
        ),
        # Also add to historical model
        migrations.AddField(
            model_name="historicalmachineinstance",
            name="asset_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Unique asset identifier (e.g., M0001). Auto-generated.",
                max_length=10,
                verbose_name="Asset ID",
            ),
        ),
        # Step 2: Backfill existing machines
        migrations.RunPython(backfill_asset_ids, reverse_backfill),
        # Step 3: Make unique on the real table (not historical)
        migrations.AlterField(
            model_name="machineinstance",
            name="asset_id",
            field=models.CharField(
                blank=True,
                help_text="Unique asset identifier (e.g., M0001). Auto-generated.",
                max_length=10,
                unique=True,
                verbose_name="Asset ID",
            ),
        ),
    ]
