"""Custom middleware helpers."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from whitenoise.middleware import WhiteNoiseMiddleware


class MediaWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    """Extend WhiteNoise so it can serve uploaded media files."""

    def __init__(self, get_response):
        super().__init__(get_response)
        self._add_media_files()

    def _add_media_files(self) -> None:
        media_root = getattr(settings, "MEDIA_ROOT", None)
        media_url = getattr(settings, "MEDIA_URL", "")
        if not media_root or not media_url.startswith("/"):
            return

        prefix = media_url.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"

        # WhiteNoise expects a string path, not Path objects.
        root = str(media_root) if isinstance(media_root, Path) else media_root
        self.add_files(root, prefix=prefix)
