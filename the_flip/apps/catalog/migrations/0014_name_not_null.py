"""Make name field required (NOT NULL) and update help text."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0013_backfill_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machineinstance",
            name="name",
            field=models.CharField(
                help_text="Display name for this machine",
                max_length=200,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicalmachineinstance",
            name="name",
            field=models.CharField(
                db_index=True,
                help_text="Display name for this machine",
                max_length=200,
            ),
        ),
    ]
