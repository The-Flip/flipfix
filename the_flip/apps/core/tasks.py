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


class TransferError(Exception):
    """Raised when HTTP file transfer fails after all retries."""


# Worker service settings for HTTP transfer
DJANGO_WEB_SERVICE_URL = config("DJANGO_WEB_SERVICE_URL", default=None)
TRANSCODING_UPLOAD_TOKEN = config("TRANSCODING_UPLOAD_TOKEN", default=None)

# FFmpeg encoding settings
MAX_VIDEO_DIMENSION = 2400  # Maximum width/height to prevent huge output files
# Allowlist of trusted binaries for subprocess calls
TRUSTED_BINARIES = frozenset({"ffmpeg", "ffprobe"})
VIDEO_CRF_QUALITY = "23"  # CRF quality (18-28 range, lower = better quality)
VIDEO_PRESET = "medium"  # Encoding speed preset (slower = better compression)
AUDIO_BITRATE = "128k"  # Audio bitrate
POSTER_WIDTH = 320  # Thumbnail width in pixels


def _get_transcoding_config(
    web_service_url: str | None = None,
    upload_token: str | None = None,
) -> tuple[str, str]:
    """
    Get and validate required transcoding configuration.

    Args:
        web_service_url: Override for DJANGO_WEB_SERVICE_URL (uses env var if None)
        upload_token: Override for TRANSCODING_UPLOAD_TOKEN (uses env var if None)

    Returns:
        Tuple of (web_service_url, upload_token) after validation

    Raises:
        ValueError: If required configuration is missing
    """
    url = web_service_url or DJANGO_WEB_SERVICE_URL
    token = upload_token or TRANSCODING_UPLOAD_TOKEN

    missing = []
    if not url:
        missing.append("DJANGO_WEB_SERVICE_URL")
    if not token:
        missing.append("TRANSCODING_UPLOAD_TOKEN")

    if missing:
        msg = f"Required environment variables not configured: {', '.join(missing)}"
        raise ValueError(msg)

    return url, token


def enqueue_transcode(media_id: int, model_name: str, *, async_runner=async_task) -> None:
    """
    Enqueue a video transcoding job.

    Args:
        media_id: ID of the media record
        model_name: Name of the media model class (e.g., "LogEntryMedia", "PartRequestMedia")
    """
    async_runner(
        transcode_video_job,
        media_id,
        model_name,
        current_log_context(),
        timeout=600,
    )


def transcode_video_job(
    media_id: int,
    model_name: str,
    log_context: dict | None = None,
    *,
    download=None,
    probe=None,
    run_ffmpeg=None,
    upload=None,
) -> None:
    """Transcode video to H.264/AAC MP4, extract poster, upload to web service."""
    token = bind_log_context(**log_context) if log_context else None

    download_fn = download or _download_source_file
    probe_fn = probe or _probe_duration_seconds
    run_ffmpeg_fn = run_ffmpeg or _run_ffmpeg
    upload_fn = upload or _upload_transcoded_files

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
    try:
        web_service_url, upload_token = _get_transcoding_config()
    except ValueError as e:
        logger.error("Transcode job %s aborted: %s", media_id, str(e))
        media.transcode_status = media_model.STATUS_FAILED
        media.save(update_fields=["transcode_status", "updated_at"])
        raise

    logger.info("Transcoding video %s (%s) for HTTP transfer to web service", media_id, model_name)

    media.transcode_status = media_model.STATUS_PROCESSING
    media.save(update_fields=["transcode_status", "updated_at"])

    tmp_source = None
    tmp_video = None
    tmp_poster = None

    try:
        # Download source file from web service
        tmp_source = download_fn(media_id, model_name, web_service_url, upload_token)
        input_path = Path(tmp_source)

        duration_seconds = probe_fn(input_path)
        if duration_seconds is not None:
            media.duration = duration_seconds
            media.save(update_fields=["duration", "updated_at"])

        tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        run_ffmpeg_fn(
            [
                "ffmpeg",
                "-i",
                str(input_path),
                "-vf",
                f"scale=min(iw\\,{MAX_VIDEO_DIMENSION}):min(ih\\,{MAX_VIDEO_DIMENSION}):force_original_aspect_ratio=decrease",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "main",
                "-crf",
                VIDEO_CRF_QUALITY,
                "-preset",
                VIDEO_PRESET,
                "-c:a",
                "aac",
                "-b:a",
                AUDIO_BITRATE,
                "-movflags",
                "+faststart",
                "-y",
                tmp_video.name,
            ]
        )

        tmp_poster = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        run_ffmpeg_fn(
            [
                "ffmpeg",
                "-i",
                str(input_path),
                "-vf",
                f"thumbnail,scale={POSTER_WIDTH}:-2",
                "-frames:v",
                "1",
                "-y",
                tmp_poster.name,
            ]
        )

        # Upload transcoded files to web service via HTTP
        upload_fn(
            media_id,
            tmp_video.name,
            tmp_poster.name,
            web_service_url,
            upload_token,
            model_name=model_name,
        )
        logger.info("Successfully uploaded transcoded video %s (%s)", media_id, model_name)

    except Exception as exc:
        logger.error(
            "Failed to transcode video %s (%s): %s", media_id, model_name, exc, exc_info=True
        )
        media.transcode_status = media_model.STATUS_FAILED
        media.save(update_fields=["transcode_status", "updated_at"])
        raise
    finally:
        # Clean up temp files (tmp_source is a path string, others are file objects)
        if tmp_source and os.path.exists(tmp_source):
            try:
                os.unlink(tmp_source)
            except OSError:
                logger.warning("Could not delete temp file %s", tmp_source)

        for tmp in (tmp_video, tmp_poster):
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    logger.warning("Could not delete temp file %s", tmp.name)

        if token:
            reset_log_context(token)


def _sleep_with_backoff(attempt: int, max_retries: int, error_detail: str) -> None:
    """
    Sleep with exponential backoff, or raise if retries exhausted.

    Args:
        attempt: Current attempt number (1-indexed)
        max_retries: Maximum attempts allowed
        error_detail: Error message for final failure

    Raises:
        Exception: If max retries exceeded
    """
    if attempt < max_retries:
        wait_time = 2**attempt  # Exponential backoff: 2s, 4s, 8s
        logger.info("Waiting %d seconds before retry...", wait_time)
        time.sleep(wait_time)
    else:
        error_msg = f"Transfer failed after {max_retries} attempts: {error_detail}"
        raise TransferError(error_msg)


def _download_source_file(
    media_id: int,
    model_name: str,
    web_service_url: str,
    upload_token: str,
    max_retries: int = 3,
) -> str:
    """
    Download source video from web service to temp file.

    Args:
        media_id: ID of media record
        model_name: Name of the media model class
        web_service_url: Base URL of web service
        upload_token: Bearer token for authentication
        max_retries: Maximum number of download attempts (default: 3)

    Returns:
        Path to downloaded temp file (caller must clean up)

    Raises:
        Exception: If download fails after all retries
    """
    download_url = (
        f"{web_service_url.rstrip('/')}/api/transcoding/download/{model_name}/{media_id}/"
    )
    headers = {"Authorization": f"Bearer {upload_token}"}

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Downloading source file for media %s from %s (attempt %d/%d)",
                media_id,
                download_url,
                attempt,
                max_retries,
            )

            response = requests.get(download_url, headers=headers, stream=True, timeout=300)

            if response.status_code == 200:
                # Get file extension from Content-Disposition or default to .mp4
                content_disp = response.headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    filename = content_disp.split("filename=")[-1].strip('"')
                    ext = Path(filename).suffix or ".mp4"
                else:
                    ext = ".mp4"

                # Stream to temp file
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                try:
                    for chunk in response.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    tmp.close()
                    logger.info(
                        "Downloaded source file for media %s to %s",
                        media_id,
                        tmp.name,
                    )
                    return tmp.name
                except Exception:
                    tmp.close()
                    if os.path.exists(tmp.name):
                        os.unlink(tmp.name)
                    raise

            # Log error and retry if not successful
            logger.warning(
                "Download attempt %d/%d failed for media %s: HTTP %d - %s",
                attempt,
                max_retries,
                media_id,
                response.status_code,
                response.text[:200] if response.text else "(no body)",
            )
            _sleep_with_backoff(attempt, max_retries, f"HTTP {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.warning(
                "Download attempt %d/%d failed for media %s: %s",
                attempt,
                max_retries,
                media_id,
                str(e),
            )
            _sleep_with_backoff(attempt, max_retries, str(e))

    # Should not reach here due to _sleep_with_backoff raising
    raise TransferError(f"Download failed after {max_retries} attempts")


def _upload_transcoded_files(
    media_id: int,
    video_path: str,
    poster_path: str,
    web_service_url: str,
    upload_token: str,
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
        web_service_url: Base URL of web service
        upload_token: Bearer token for authentication
        max_retries: Maximum number of upload attempts (default: 3)
        model_name: Name of the media model class (default: LogEntryMedia)

    Raises:
        Exception: If upload fails after all retries
    """
    upload_url = f"{web_service_url.rstrip('/')}/api/transcoding/upload/{model_name}/{media_id}/"
    headers = {"Authorization": f"Bearer {upload_token}"}

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

                response = requests.post(upload_url, files=files, headers=headers, timeout=300)

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
            _sleep_with_backoff(attempt, max_retries, f"HTTP {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.warning(
                "Upload attempt %d/%d failed for media %s: %s",
                attempt,
                max_retries,
                media_id,
                str(e),
            )
            _sleep_with_backoff(attempt, max_retries, str(e))


def _probe_duration_seconds(input_path: Path) -> int | None:
    """Return duration in whole seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_entries",
        "format=duration",
        str(input_path),
    ]
    if cmd[0] not in TRUSTED_BINARIES:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        if duration is None:
            return None
        return int(float(duration))
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError, OSError):
        return None


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run ffmpeg/ffprobe with basic logging."""
    if cmd[0] not in TRUSTED_BINARIES:
        raise ValueError(f"Untrusted binary: {cmd[0]}")
    logger.info("Running command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
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
