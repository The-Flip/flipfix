"""Add the ``submission_id`` idempotency token to LogEntry.

Low-risk rollout: ``submission_id`` is a new nullable column, so there is no
data backfill and existing rows stay ``NULL``.  Building the ``UNIQUE`` index
takes a brief lock, which is negligible for this table (order thousands of rows
for a single museum).  Fully reversible (drops the column).  Should the table
ever grow large enough for the index build to matter on Postgres, switch to
``CREATE UNIQUE INDEX CONCURRENTLY`` via ``SeparateDatabaseAndState`` + ``RunSQL``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0020_seed_maintenance_task_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicallogentry',
            name='submission_id',
            field=models.UUIDField(blank=True, db_index=True, help_text='Idempotency token supplied by the client (web form render or API call). Collapses accidental resubmits from a slow or timed-out connection. NULL for entries created without a token.', null=True),
        ),
        migrations.AddField(
            model_name='logentry',
            name='submission_id',
            field=models.UUIDField(blank=True, help_text='Idempotency token supplied by the client (web form render or API call). Collapses accidental resubmits from a slow or timed-out connection. NULL for entries created without a token.', null=True, unique=True),
        ),
    ]
