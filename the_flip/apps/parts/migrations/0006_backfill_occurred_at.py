# Generated manually
"""Backfill occurred_at from created_at for existing PartRequest and PartRequestUpdate records."""

from django.db import migrations


def backfill_occurred_at(apps, schema_editor):
    """Set occurred_at to created_at for existing records."""
    PartRequest = apps.get_model("parts", "PartRequest")
    for request in PartRequest.objects.all():
        request.occurred_at = request.created_at
        request.save(update_fields=["occurred_at"])

    PartRequestUpdate = apps.get_model("parts", "PartRequestUpdate")
    for update in PartRequestUpdate.objects.all():
        update.occurred_at = update.created_at
        update.save(update_fields=["occurred_at"])


def reverse_backfill(apps, schema_editor):
    """No action needed - fields will be dropped in reverse."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("parts", "0005_partrequest_occurred_at_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_occurred_at, reverse_backfill),
    ]
