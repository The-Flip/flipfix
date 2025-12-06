"""Core background tasks for media processing."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from decouple import config
from django_q.tasks import async_task

from the_flip.apps.core.models import get_media_model
from the_flip.logging import bind_log_context, current_log_context, reset_log_context

logger = logging.getLogger(__name__)

# Worker service settings for HTTP transfer
DJANGO_WEB_SERVICE_URL = config("DJANGO_WEB_SERVICE_URL", default=None)
TRANSCODING_UPLOAD_TOKEN = config("TRANSCODING_UPLOAD_TOKEN", default=None)


def enqueue_transcode(media_id: int, model_name: str) -> None:
    """
    Enqueue a video transcoding job.

    Args:
        media_id: ID of the media record
        model_name: Name of the media model class (e.g., "LogEntryMedia", "PartRequestMedia")
    """
    async_task(
        transcode_video_job,
        media_id,
        model_name,
        current_log_context(),
        timeout=600,
    )


def transcode_video_job(media_id: int, model_name: str, log_context: dict | None = None) -> None:
    """Transcode video to H.264/AAC MP4, extract poster, upload to web service."""
    token = bind_log_context(**log_context) if log_context else None

    try:
        media_model = get_media_model(model_name)
        media = media_model.objects.get(id=media_id)
    except Exception:
        logger.error("Transcode job %s (%s) aborted: media not found", media_id, model_name)
        return

    if media.media_type != media_model.TYPE_VIDEO:
        logger.info("Transcode skipped for non-video media %s", media_id)
        return

    # Validate HTTP transfer configuration
    missing = []
    if not DJANGO_WEB_SERVICE_URL:
        missing.append("DJANGO_WEB_SERVICE_URL")
    if not TRANSCODING_UPLOAD_TOKEN:
        missing.append("TRANSCODING_UPLOAD_TOKEN")

    if missing:
        msg = f"Required environment variables not configured: {', '.join(missing)}"
        logger.error("Transcode job %s aborted: %s", media_id, msg)
        media.transcode_status = media_model.STATUS_FAILED
        media.save(update_fields=["transcode_status", "updated_at"])
        raise ValueError(msg)

    logger.info("Transcoding video %s (%s) for HTTP transfer to web service", media_id, model_name)

    input_path = Path(media.file.path)
    media.transcode_status = media_model.STATUS_PROCESSING
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

        # Upload transcoded files to web service via HTTP
        _upload_transcoded_files(media_id, tmp_video.name, tmp_poster.name, model_name=model_name)
        logger.info("Successfully uploaded transcoded video %s (%s)", media_id, model_name)

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to transcode video %s (%s): %s", media_id, model_name, exc, exc_info=True
        )
        media.transcode_status = media_model.STATUS_FAILED
        media.save(update_fields=["transcode_status", "updated_at"])
        raise
    finally:
        for tmp in (tmp_video, tmp_poster):
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    logger.warning("Could not delete temp file %s", tmp.name)

        if token:
            reset_log_context(token)


def _upload_transcoded_files(
    media_id: int,
    video_path: str,
    poster_path: str,
    max_retries: int = 3,
    model_name: str = "LogEntryMedia",
) -> None:
    """
    Upload transcoded video and poster to Django web service via HTTP.

    Implements retry logic with exponential backoff.

    Args:
        media_id: ID of media record
        video_path: Path to transcoded video file
        poster_path: Path to poster image file
        max_retries: Maximum number of upload attempts (default: 3)
        model_name: Name of the media model class (default: LogEntryMedia)

    Raises:
        Exception: If upload fails after all retries
    """
    missing = []
    if not DJANGO_WEB_SERVICE_URL:
        missing.append("DJANGO_WEB_SERVICE_URL")
    if not TRANSCODING_UPLOAD_TOKEN:
        missing.append("TRANSCODING_UPLOAD_TOKEN")

    if missing:
        msg = f"Required environment variables not configured: {', '.join(missing)}"
        raise ValueError(msg)

    upload_url = f"{DJANGO_WEB_SERVICE_URL.rstrip('/')}/api/transcoding/upload/"
    headers = {"Authorization": f"Bearer {TRANSCODING_UPLOAD_TOKEN}"}

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Uploading transcoded files for media %s to %s (attempt %d/%d)",
                media_id,
                upload_url,
                attempt,
                max_retries,
            )

            with open(video_path, "rb") as video_file, open(poster_path, "rb") as poster_file:
                files = {
                    "video_file": ("video.mp4", video_file, "video/mp4"),
                    "poster_file": ("poster.jpg", poster_file, "image/jpeg"),
                }
                data = {
                    "media_id": str(media_id),
                    "model_name": model_name,
                    # Keep legacy field for backward compatibility
                    "log_entry_media_id": str(media_id),
                }

                response = requests.post(
                    upload_url, files=files, data=data, headers=headers, timeout=300
                )

            if response.status_code == 200:
                result = response.json()
                logger.info("Upload successful for media %s: %s", media_id, result.get("message"))
                return

            # Log error and retry if not successful
            logger.warning(
                "Upload attempt %d/%d failed for media %s: HTTP %d - %s",
                attempt,
                max_retries,
                media_id,
                response.status_code,
                response.text[:200],
            )

            if attempt < max_retries:
                # Exponential backoff: 2^attempt seconds (2s, 4s, 8s)
                wait_time = 2**attempt
                logger.info("Waiting %d seconds before retry...", wait_time)
                time.sleep(wait_time)
            else:
                # Final attempt failed
                error_msg = (
                    f"Upload failed after {max_retries} attempts: HTTP {response.status_code}"
                )
                raise Exception(error_msg)  # noqa: TRY002

        except requests.exceptions.RequestException as e:
            logger.warning(
                "Upload attempt %d/%d failed for media %s: %s",
                attempt,
                max_retries,
                media_id,
                str(e),
            )

            if attempt < max_retries:
                wait_time = 2**attempt
                logger.info("Waiting %d seconds before retry...", wait_time)
                time.sleep(wait_time)
            else:
                error_msg = f"Upload failed after {max_retries} attempts: {e}"
                raise Exception(error_msg) from e  # noqa: TRY002


def _probe_duration_seconds(input_path: Path) -> int | None:
    """Return duration in whole seconds using ffprobe."""
    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607 - trusted ffprobe binary
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


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run ffmpeg/ffprobe with basic logging."""
    logger.info("Running command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603
        if result.stdout:
            logger.debug("FFmpeg stdout: %s", result.stdout)
        if result.stderr:
            logger.debug("FFmpeg stderr: %s", result.stderr)
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg command failed with exit code %d", e.returncode)
        if e.stdout:
            logger.error("FFmpeg stdout: %s", e.stdout)
        if e.stderr:
            logger.error("FFmpeg stderr: %s", e.stderr)
        raise
