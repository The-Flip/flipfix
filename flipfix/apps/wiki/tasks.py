"""Background tasks for the wiki app (run by the django-q worker)."""

from __future__ import annotations

import logging

from django.urls import reverse

from flipfix.apps.core.web_service import post_to_web_service

logger = logging.getLogger(__name__)


def delete_orphaned_wiki_media() -> int:
    """Have the web service delete wiki media no page references.

    Runs daily via a Schedule registered by the ``ensure_scheduled_tasks``
    management command. The sweep itself runs on the web service, which has
    the media disk; this worker task only triggers it. Errors propagate so a
    failed run is recorded by django-q.
    """
    deleted = post_to_web_service(reverse("api-wiki-media-sweep"))["deleted"]
    if deleted:
        logger.info("Deleted %d orphaned wiki media file(s)", deleted)
    return deleted
