"""Background tasks for the wiki app (run by the django-q worker)."""

from __future__ import annotations

import logging

from .media import delete_orphaned_media

logger = logging.getLogger(__name__)


def delete_orphaned_wiki_media() -> int:
    """Delete wiki media no page references.

    Runs daily via a Schedule registered by the ``ensure_scheduled_tasks``
    management command.
    """
    deleted = delete_orphaned_media()
    if deleted:
        logger.info("Deleted %d orphaned wiki media file(s)", deleted)
    return deleted
