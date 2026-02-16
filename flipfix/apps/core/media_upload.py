"""Media upload orchestration.

Bridges media configuration (``media.py``) and background transcoding
(``transcoding.py``) so that callers don't need to know about both.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from flipfix.apps.core.media import is_video_file
from flipfix.apps.core.transcoding import enqueue_transcode


def attach_media_files(
    *,
    media_files: Sequence[UploadedFile],
    parent: object,
    media_model: type[Any],
) -> list[Any]:
    """Create media records for uploaded files and enqueue video transcoding.

    ``media_model`` must be a concrete ``AbstractMedia`` subclass
    (e.g. ``LogEntryMedia``).  The type is ``Any`` because django-stubs
    does not expose ``.objects`` on abstract model types.

    Must be called inside a transaction (e.g. a view decorated with
    ``@transaction.atomic``) so that ``on_commit`` callbacks fire correctly.
    """
    created: list[Any] = []
    for media_file in media_files:
        is_video = is_video_file(media_file)

        media = media_model.objects.create(
            **{media_model.parent_field_name: parent},
            media_type=media_model.MediaType.VIDEO if is_video else media_model.MediaType.PHOTO,
            file=media_file,
            transcode_status=media_model.TranscodeStatus.PENDING if is_video else "",
        )

        if is_video:
            transaction.on_commit(
                partial(enqueue_transcode, media_id=media.id, model_name=media_model.__name__)
            )

        created.append(media)
    return created
