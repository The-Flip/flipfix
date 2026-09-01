"""Drop ``Invitation.used``, now superseded by ``accepted_at``.

Separate from 0014 so that 0015's backfill still has the column to read.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_backfill_invitation_acceptance"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="invitation",
            name="used",
        ),
    ]
