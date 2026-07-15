"""One-time cleanup: mark machines with an open Unplayable report as Broken.

Enforces the invariant introduced alongside this migration (see
``flipfix.apps.maintenance.status_rules``).  One-directional and irreversible:
we can't tell a machine broken by this cleanup from one broken for other
reasons, so the reverse is a no-op.
"""

from django.db import migrations

from flipfix.apps.maintenance.reconcile_machine_status import (
    reconcile_unplayable_machine_status,
)


def forward(apps, schema_editor):
    reconcile_unplayable_machine_status(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0023_seed_check_replace_lights_task"),
        ("catalog", "0021_merge_20260316_0036"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
