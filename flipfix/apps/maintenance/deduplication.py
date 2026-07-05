"""De-duplication of ``LogEntry`` rows created by retried submissions.

Before :attr:`LogEntry.submission_id <flipfix.apps.maintenance.models.LogEntry>`
existed, a maintainer whose submission was retried on a slow or timed-out
connection inserted a second identical row.  This module collapses those
historical duplicates.

The entry point takes the Django ``apps`` registry rather than concrete model
classes so it runs unchanged against the frozen models inside a data migration
(the ``apps`` handed to ``RunPython``) and the real models from a management
command or a test (``from django.apps import apps``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from django.db.models import Count

# Two submissions with identical content by the same author within this window
# are treated as one retried submission rather than two intentional entries.
DUPLICATE_WINDOW = timedelta(minutes=2)

# Fields that identify "the same submission by the same author".  occurred_at is
# deliberately excluded: the web form pins it to a minute-precision value (retries
# share it) but the API defaults it to now() (retries differ by seconds), so
# grouping on it would miss API retries.  created_at proximity is used instead.
_GROUP_FIELDS = ("machine_id", "problem_report_id", "text", "created_by_id", "maintainer_names")


def _duplicate_clusters(rows, window):
    """Group ``created_at``-ordered rows into duplicate bursts.

    All rows in a cluster fall within ``window`` of the cluster's *first* row, so
    a cluster can never span more than ``window`` — anchoring to the first row
    (rather than the previous one) stops a slow chain of near-matches from
    snowballing into one oversized cluster and collapsing a genuine entry.
    Returns only the clusters that actually repeat (more than one row).
    """
    clusters: list[list] = []
    current: list = []
    for row in rows:
        if current and row.created_at - current[0].created_at > window:
            clusters.append(current)
            current = []
        current.append(row)
    if current:
        clusters.append(current)
    return [cluster for cluster in clusters if len(cluster) > 1]


def _merge_cluster(cluster, log_entry_cls, log_entry_media, record_reference, log_entry_ct):
    """Fold a duplicate cluster onto its earliest entry, returning stats.

    Repoints the losers' media to the survivor (never lose an attachment),
    unions their maintainers and tasks onto the survivor, prunes the losers'
    markdown-link references, then deletes the losers.
    """
    survivor, *losers = cluster
    loser_pks = [loser.pk for loser in losers]

    media_repointed = log_entry_media.objects.filter(log_entry_id__in=loser_pks).update(
        log_entry_id=survivor.pk
    )

    for loser in losers:
        survivor.maintainers.add(*loser.maintainers.all())
        survivor.maintenance_tasks.add(*loser.maintenance_tasks.all())

    # The post_delete cleanup signal is bound to the real model, so it does not
    # fire for frozen-model deletes inside a migration — prune references here.
    if log_entry_ct is not None:
        record_reference.objects.filter(source_type=log_entry_ct, source_id__in=loser_pks).delete()

    log_entry_cls.objects.filter(pk__in=loser_pks).delete()
    return len(loser_pks), media_repointed


def deduplicate_log_entries(apps, *, window=DUPLICATE_WINDOW, log: Callable[[str], None] = print):
    """Collapse duplicate ``LogEntry`` rows created by retried submissions.

    For each set of entries sharing ``(machine, problem_report, text, author,
    maintainer_names)`` and clustered within ``window`` of each other, keep the
    earliest and fold the rest into it (see :func:`_merge_cluster`).

    ``apps`` is the Django app registry (frozen models in a migration, real
    models otherwise).  Returns a summary dict and emits a one-line summary via
    ``log`` (defaults to :func:`print`) so a migration run records what it did.
    """
    log_entry = apps.get_model("maintenance", "LogEntry")
    log_entry_media = apps.get_model("maintenance", "LogEntryMedia")
    content_type = apps.get_model("contenttypes", "ContentType")
    record_reference = apps.get_model("core", "RecordReference")

    # A LogEntry reference can only exist if its ContentType row does, so a
    # missing ContentType simply means there is nothing to prune.
    log_entry_ct = content_type.objects.filter(app_label="maintenance", model="logentry").first()

    # DB-level first pass: only groups that actually repeat are worth loading.
    candidate_groups = (
        log_entry.objects.values(*_GROUP_FIELDS).annotate(n=Count("id")).filter(n__gt=1)
    )

    clusters_found = rows_deleted = media_repointed = 0

    for group in candidate_groups:
        rows = list(
            log_entry.objects.filter(**{field: group[field] for field in _GROUP_FIELDS}).order_by(
                "created_at", "pk"
            )
        )
        for cluster in _duplicate_clusters(rows, window):
            clusters_found += 1
            deleted, repointed = _merge_cluster(
                cluster, log_entry, log_entry_media, record_reference, log_entry_ct
            )
            rows_deleted += deleted
            media_repointed += repointed

    log(
        f"deduplicate_log_entries: collapsed {clusters_found} duplicate cluster(s), "
        f"deleted {rows_deleted} row(s), repointed {media_repointed} media file(s)."
    )
    return {
        "clusters": clusters_found,
        "deleted": rows_deleted,
        "media_repointed": media_repointed,
    }
