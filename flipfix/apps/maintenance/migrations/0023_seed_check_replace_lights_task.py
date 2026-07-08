from django.db import migrations

# Adds "Check/replace lights" to the recurring-maintenance vocabulary. Follows
# the same pattern as 0020: slug is set explicitly because the historical model
# used by migrations does not run MaintenanceTaskType.save() (which would
# otherwise auto-fill the slug). sort_order continues the 10-step sequence.
SEEDS = [
    {"name": "Check/replace lights", "slug": "check-replace-lights", "sort_order": 40},
]


def seed(apps, schema_editor):
    MaintenanceTaskType = apps.get_model("maintenance", "MaintenanceTaskType")
    for entry in SEEDS:
        MaintenanceTaskType.objects.get_or_create(slug=entry["slug"], defaults=entry)


def unseed(apps, schema_editor):
    MaintenanceTaskType = apps.get_model("maintenance", "MaintenanceTaskType")
    MaintenanceTaskType.objects.filter(slug__in=[e["slug"] for e in SEEDS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0022_dedupe_log_entries"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
