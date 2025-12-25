"""Rename name_override to name on MachineInstance."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_make_era_optional"),
    ]

    operations = [
        migrations.RenameField(
            model_name="machineinstance",
            old_name="name_override",
            new_name="name",
        ),
        migrations.RenameField(
            model_name="historicalmachineinstance",
            old_name="name_override",
            new_name="name",
        ),
    ]
