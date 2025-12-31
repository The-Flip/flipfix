# Generated manually
"""Backfill occurred_at from created_at for existing ProblemReport records."""

from django.db import migrations


def backfill_occurred_at(apps, schema_editor):
    """Set occurred_at to created_at for existing problem reports and history."""
    ProblemReport = apps.get_model("maintenance", "ProblemReport")
    for report in ProblemReport.objects.all():
        report.occurred_at = report.created_at
        report.save(update_fields=["occurred_at"])

    # Also backfill historical records - they got default=timezone.now during
    # the schema migration, but should reflect the original created_at timestamp
    HistoricalProblemReport = apps.get_model("maintenance", "HistoricalProblemReport")
    for historical in HistoricalProblemReport.objects.all():
        historical.occurred_at = historical.created_at
        historical.save(update_fields=["occurred_at"])


def reverse_backfill(apps, schema_editor):
    """No action needed - field will be dropped in reverse."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0011_alter_logentry_options_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_occurred_at, reverse_backfill),
    ]
