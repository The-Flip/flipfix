"""Add Owner model and FK on MachineInstance.

Steps:
1. Create Owner table
2. Seed initial owners ("The Flip", "William Pietri")
3. Add owner FK to MachineInstance (nullable)
4. Assign all existing machines to "William Pietri"
5. Remove ownership_credit field
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify


def seed_owners_and_assign(apps, schema_editor):
    """Create initial owners and assign all machines to William Pietri."""
    Owner = apps.get_model("catalog", "Owner")
    MachineInstance = apps.get_model("catalog", "MachineInstance")

    Owner.objects.create(name="The Flip", slug="the-flip")
    william = Owner.objects.create(name="William Pietri", slug="william-pietri")

    MachineInstance.objects.all().update(owner=william)


def reverse_seed(apps, schema_editor):
    """Remove seeded owners (machines will have owner set to NULL by cascade)."""
    Owner = apps.get_model("catalog", "Owner")
    Owner.objects.filter(slug__in=["the-flip", "william-pietri"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0015_add_asset_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Create Owner table
        migrations.CreateModel(
            name="Owner",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=200, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=50)),
                (
                    "alternate_contact",
                    models.TextField(blank=True, help_text="Additional contact information"),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owners_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owners_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        # Create historical Owner table
        migrations.CreateModel(
            name="HistoricalOwner",
            fields=[
                (
                    "id",
                    models.IntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID"),
                ),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("name", models.CharField(db_index=True, max_length=200)),
                ("slug", models.SlugField(max_length=200)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=50)),
                (
                    "alternate_contact",
                    models.TextField(blank=True, help_text="Additional contact information"),
                ),
                ("notes", models.TextField(blank=True)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical owner",
                "verbose_name_plural": "historical owners",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
        ),
        # Step 2: Add owner FK to MachineInstance (nullable)
        migrations.AddField(
            model_name="machineinstance",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="Person or company that owns this machine",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="machines",
                to="catalog.owner",
            ),
        ),
        # Add owner FK to historical table
        migrations.AddField(
            model_name="historicalmachineinstance",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Person or company that owns this machine",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="catalog.owner",
            ),
        ),
        # Step 3: Seed owners and assign machines
        migrations.RunPython(seed_owners_and_assign, reverse_seed),
        # Step 4: Remove ownership_credit
        migrations.RemoveField(
            model_name="machineinstance",
            name="ownership_credit",
        ),
        migrations.RemoveField(
            model_name="historicalmachineinstance",
            name="ownership_credit",
        ),
    ]
