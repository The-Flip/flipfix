"""Background tasks for maintenance media."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from django.core.files import File
from django_q.tasks import async_task

from the_flip.apps.maintenance.models import LogEntryMedia

logger = logging.getLogger(__name__)


def enqueue_transcode(media_id: int):
    """Enqueue transcode job."""
    async_task(transcode_video_job, media_id, timeout=600)


def transcode_video_job(media_id: int):
    """Transcode video to H.264/AAC MP4, extract poster, save metadata, delete original."""
    try:
        media = LogEntryMedia.objects.get(id=media_id)
    except LogEntryMedia.DoesNotExist:
        logger.error("Transcode job %s aborted: media not found", media_id)
        return

    if media.media_type != LogEntryMedia.TYPE_VIDEO:
        logger.info("Transcode skipped for non-video media %s", media_id)
        return

    input_path = Path(media.file.path)
    media.transcode_status = LogEntryMedia.STATUS_PROCESSING
    media.save(update_fields=["transcode_status", "updated_at"])

    tmp_video = None
    tmp_poster = None

    try:
        duration_seconds = _probe_duration_seconds(input_path)
        if duration_seconds is not None:
            media.duration = duration_seconds
            media.save(update_fields=["duration", "updated_at"])

        tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        _run_ffmpeg(
            [
                "ffmpeg",
                "-i",
                str(input_path),
                "-vf",
                "scale=min(iw\\,2400):min(ih\\,2400):force_original_aspect_ratio=decrease",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "main",
                "-crf",
                "23",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-y",
                tmp_video.name,
            ]
        )

        with open(tmp_video.name, "rb") as f:
            media.transcoded_file.save(f"video_{media.id}.mp4", File(f), save=False)

        tmp_poster = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        _run_ffmpeg(
            [
                "ffmpeg",
                "-i",
                str(input_path),
                "-vf",
                "thumbnail,scale=320:-2",
                "-frames:v",
                "1",
                "-y",
                tmp_poster.name,
            ]
        )

        with open(tmp_poster.name, "rb") as f:
            media.poster_file.save(f"poster_{media.id}.jpg", File(f), save=False)

        media.file.delete(save=False)

        media.transcode_status = LogEntryMedia.STATUS_READY
        media.save(update_fields=["transcoded_file", "poster_file", "transcode_status", "updated_at"])
        logger.info("Successfully transcoded video %s", media_id)

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to transcode video %s: %s", media_id, exc, exc_info=True)
        media.transcode_status = LogEntryMedia.STATUS_FAILED
        media.save(update_fields=["transcode_status", "updated_at"])
        raise
    finally:
        for tmp in (tmp_video, tmp_poster):
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    logger.warning("Could not delete temp file %s", tmp.name)


def _probe_duration_seconds(input_path: Path) -> int | None:
    """Return duration in whole seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_entries",
                "format=duration",
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        if duration is None:
            return None
        return int(float(duration))
    except Exception:  # noqa: BLE001
        return None


def _run_ffmpeg(cmd: list[str]):
    """Run ffmpeg/ffprobe with basic logging."""
    logger.info("Running command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
