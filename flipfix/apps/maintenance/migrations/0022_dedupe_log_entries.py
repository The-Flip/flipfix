"""Collapse historical duplicate log entries created by retried submissions.

Before ``LogEntry.submission_id`` existed, a slow or timed-out connection that
the maintainer retried inserted a second identical row.  This one-time migration
folds those duplicates together — keeping the earliest and preserving media and
maintainers.  The logic lives in :mod:`flipfix.apps.maintenance.deduplication`
so it can also be exercised from tests and an on-demand management command.

Irreversible: deletions cannot be un-done, so the reverse is a no-op.

Assumes it runs against historical data without concurrent write traffic — every
log entry created after this deploy carries a ``submission_id`` and is protected
at write time, so there is nothing new for this one-time pass to race with.
"""

from django.db import migrations

from flipfix.apps.maintenance.deduplication import deduplicate_log_entries


def forward(apps, schema_editor):
    deduplicate_log_entries(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0021_logentry_submission_id"),
        # RecordReference (core) and ContentType are read during cleanup; depend
        # on the migration that creates RecordReference so it exists in state.
        ("core", "0001_add_record_reference"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
