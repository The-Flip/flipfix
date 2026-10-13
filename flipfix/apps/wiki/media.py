"""Wiki media: upload, reference tracking, and orphan cleanup.

Media is embedded in wiki markdown by a stable app URL
(``![alt](/wiki/media/<pk>/)``) rather than a storage path, so stored
content survives a change of storage backend. See ``WikiMedia`` for the
ownership model. Only images can be uploaded so far.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from flipfix.apps.core.image_processing import resize_image_file

from .models import WikiMedia, WikiPage

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)

MAX_WIKI_IMAGE_BYTES = 25 * 1024 * 1024
"""Upload cap for wiki images. Lower than the general media cap, which exists for video."""

ORPHAN_GRACE_PERIOD = timedelta(days=7)
"""How long unreferenced media survives after upload, so a page being created
(possibly in a form left open for days) has time to be saved."""

# Matches the path of the ``wiki-media`` route, with or without a scheme/host.
_MEDIA_REF_RE = re.compile(r"/wiki/media/(\d+)/")


def media_markdown(media: WikiMedia, alt: str) -> str:
    """Return the markdown that embeds ``media``."""
    # Square brackets in alt text would end the markdown alt span early.
    safe_alt = alt.replace("[", "").replace("]", "").strip()
    return f"![{safe_alt}]({media.get_absolute_url()})"


def alt_text_from_filename(filename: str) -> str:
    """Derive placeholder alt text from an uploaded file name ("my_photo.jpg" -> "my photo")."""
    return re.sub(r"[-_]+", " ", Path(filename).stem).strip() or "image"


def create_wiki_image(
    *,
    file: UploadedFile,
    uploaded_by: User | None,
    page: WikiPage | None = None,
) -> WikiMedia:
    """Store an uploaded image, resized for the web, optionally linked to a page.

    The file must already be validated as an image. Images uploaded while a
    page is being created have no page yet; ``record_media_references`` links
    them when the page is saved. An upload from the edit page is linked at
    once, so it stays with the page even if that edit is abandoned.
    """
    web_file = resize_image_file(file)
    with transaction.atomic():
        media = WikiMedia.objects.create(file=web_file, uploaded_by=uploaded_by)
        if page is not None:
            media.pages.add(page)
    return media


def referenced_media_ids(content: str) -> set[int]:
    """Return the ids of wiki media referenced in markdown content."""
    return {int(pk) for pk in _MEDIA_REF_RE.findall(content or "")}


def record_media_references(page: WikiPage) -> None:
    """Link all media referenced in the page's content to the page.

    Only ever adds links. Removing media from the content keeps the link,
    so earlier revisions of the page still render it.
    """
    ids = referenced_media_ids(page.content)
    if ids:
        page.media.add(*WikiMedia.objects.filter(pk__in=ids))


def _pages_embedding(media: WikiMedia):
    """Pages whose current content embeds ``media``."""
    return WikiPage.objects.filter(content__contains=media.get_absolute_url())


def delete_orphaned_media() -> int:
    """Delete media no page references, along with their files.

    As a safety net, media still embedded in some page's current content is
    linked to that page instead of deleted, in case a code path saved page
    content without calling ``record_media_references``.

    Returns the number of media records deleted.
    """
    cutoff = timezone.now() - ORPHAN_GRACE_PERIOD
    deleted = 0
    for media in list(WikiMedia.objects.orphaned(uploaded_before=cutoff)):
        embedding = list(_pages_embedding(media))
        if embedding:
            logger.warning(
                "Wiki media %s was embedded but unlinked; linking it to %d page(s)",
                media.pk,
                len(embedding),
            )
            media.pages.add(*embedding)
            continue
        names = [media.file.name] if media.file else []
        with transaction.atomic():
            # Re-check orphan status at delete time: a page saved since the
            # query above may have just linked this media.
            _, per_model = (
                WikiMedia.objects.orphaned(uploaded_before=cutoff).filter(pk=media.pk).delete()
            )
            if not per_model.get(WikiMedia._meta.label):
                continue
            transaction.on_commit(partial(_delete_files, names=names))
        deleted += 1
    return deleted


def _delete_files(*, names: list[str]) -> None:
    """Delete stored files, logging rather than raising on failure."""
    for name in names:
        try:
            default_storage.delete(name)
        except OSError:
            logger.warning("Could not delete wiki media file %s", name, exc_info=True)
