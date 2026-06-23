from django.db import migrations

# Initial recurring-maintenance vocabulary. The list grows in admin from here;
# slugs are set explicitly because the historical model used by migrations does
# not run MaintenanceTaskType.save() (which would otherwise auto-fill the slug).
SEEDS = [
    {"name": "Clean the playfield", "slug": "clean-playfield", "sort_order": 10},
    {"name": "Replace the balls", "slug": "replace-balls", "sort_order": 20},
    {"name": "Check/replace elastic bands", "slug": "replace-rubbers", "sort_order": 30},
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
        ("maintenance", "0019_maintenancetasktype_logentry_maintenance_tasks"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
