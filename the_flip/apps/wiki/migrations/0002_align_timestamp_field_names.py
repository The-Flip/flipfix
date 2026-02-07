"""Rename modified_at -> updated_at and modified_by -> updated_by.

Aligns WikiPage with the project convention (TimeStampedMixin uses
``updated_at``; catalog models use ``updated_by``).  Also adds an
index on ``updated_at`` for recency sorting on wiki home/search.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("wiki", "0001_initial"),
    ]

    operations = [
        # --- WikiPage ---
        migrations.RenameField(
            model_name="wikipage",
            old_name="modified_at",
            new_name="updated_at",
        ),
        migrations.RenameField(
            model_name="wikipage",
            old_name="modified_by",
            new_name="updated_by",
        ),
        migrations.AlterField(
            model_name="wikipage",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="wikipage",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="wikipage",
            index=models.Index(fields=["updated_at"], name="wiki_wikipa_updated_1cf336_idx"),
        ),
        # --- HistoricalWikiPage ---
        migrations.RenameField(
            model_name="historicalwikipage",
            old_name="modified_at",
            new_name="updated_at",
        ),
        migrations.RenameField(
            model_name="historicalwikipage",
            old_name="modified_by",
            new_name="updated_by",
        ),
        migrations.AlterField(
            model_name="historicalwikipage",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="historicalwikipage",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
