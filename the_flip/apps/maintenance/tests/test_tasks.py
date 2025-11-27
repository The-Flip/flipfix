"""Tests for maintenance background tasks."""

import logging
import subprocess
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from the_flip.apps.core.test_utils import create_machine
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia


@tag("tasks", "unit")
class TranscodeVideoJobTests(TestCase):
    """Tests for transcode_video_job task."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.machine = create_machine()
        self.log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test entry with video",
        )
        # Create a media record with a fake video file
        self.video_file = SimpleUploadedFile(
            "test.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_VIDEO,
            file=self.video_file,
            transcode_status=LogEntryMedia.STATUS_PENDING,
        )

    @patch("the_flip.apps.maintenance.tasks.DJANGO_WEB_SERVICE_URL", None)
    @patch("the_flip.apps.maintenance.tasks.TRANSCODING_UPLOAD_TOKEN", None)
    @patch("the_flip.apps.maintenance.tasks._upload_transcoded_files")
    @patch("the_flip.apps.maintenance.tasks._run_ffmpeg")
    @patch("the_flip.apps.maintenance.tasks._probe_duration_seconds", return_value=120)
    def test_transcode_raises_without_required_config(
        self, mock_probe, mock_run_ffmpeg, mock_upload
    ):
        """Task raises ValueError when DJANGO_WEB_SERVICE_URL is not configured."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        with self.assertRaises(ValueError) as context:
            transcode_video_job(self.media.id)

        self.assertIn("DJANGO_WEB_SERVICE_URL", str(context.exception))
        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        mock_probe.assert_not_called()
        mock_run_ffmpeg.assert_not_called()
        mock_upload.assert_not_called()

    def test_transcode_skips_nonexistent_media(self):
        """Task silently skips non-existent media IDs."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Should not raise, just log and return
        transcode_video_job(999999)  # Non-existent ID

    def test_transcode_skips_non_video_media(self):
        """Task skips non-video media types without processing."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Change media type to photo
        self.media.media_type = LogEntryMedia.TYPE_PHOTO
        self.media.save()

        # Should not process, just return
        transcode_video_job(self.media.id)
        self.media.refresh_from_db()
        # Status should remain pending (not changed)
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_PENDING)


@tag("tasks", "unit")
class TranscodeVideoErrorHandlingTests(TestCase):
    """Tests for transcode error handling."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.machine = create_machine()
        self.log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test entry with video",
        )
        self.video_file = SimpleUploadedFile(
            "test.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_VIDEO,
            file=self.video_file,
            transcode_status=LogEntryMedia.STATUS_PENDING,
        )

    @patch("the_flip.apps.maintenance.tasks.DJANGO_WEB_SERVICE_URL", "http://test.com")
    @patch("the_flip.apps.maintenance.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    @patch("the_flip.apps.maintenance.tasks._run_ffmpeg")
    @patch("the_flip.apps.maintenance.tasks._upload_transcoded_files")
    @patch("the_flip.apps.maintenance.tasks._probe_duration_seconds", return_value=120)
    def test_transcode_sets_failed_status_when_ffmpeg_errors(
        self, mock_probe, mock_upload, mock_ffmpeg
    ):
        """Task sets status to FAILED when ffmpeg exits with error."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Simulate ffmpeg failing with non-zero exit code
        mock_ffmpeg.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg", "-i", "input.mp4"],
            stderr="Error: corrupt input file",
        )

        with self.assertRaises(subprocess.CalledProcessError):
            transcode_video_job(self.media.id)

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        mock_probe.assert_called_once()
        mock_upload.assert_not_called()

    @patch("the_flip.apps.maintenance.tasks.DJANGO_WEB_SERVICE_URL", "http://test.com")
    @patch("the_flip.apps.maintenance.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    @patch("the_flip.apps.maintenance.tasks._run_ffmpeg")
    @patch("the_flip.apps.maintenance.tasks._upload_transcoded_files")
    @patch("the_flip.apps.maintenance.tasks._probe_duration_seconds", return_value=120)
    def test_transcode_fails_when_source_file_missing(self, mock_probe, mock_upload, mock_ffmpeg):
        """Task sets status to FAILED when source file cannot be read."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Simulate ffmpeg failing when reading input (e.g., missing file)
        mock_ffmpeg.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg", "-i", str(self.media.file.path)],
            stderr="No such file or directory",
        )

        with self.assertRaises(subprocess.CalledProcessError):
            transcode_video_job(self.media.id)

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        mock_probe.assert_called_once()
        mock_upload.assert_not_called()


@tag("tasks", "unit")
class EnqueueTranscodeTests(TestCase):
    """Tests for enqueue_transcode helper."""

    @patch("the_flip.apps.maintenance.tasks.async_task")
    def test_enqueue_transcode_invokes_async_task_with_media_id(self, mock_async_task):
        """enqueue_transcode schedules async task with correct parameters."""
        from the_flip.apps.maintenance.tasks import enqueue_transcode

        enqueue_transcode(123)

        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][1], 123)  # media_id argument
        self.assertEqual(call_args[1]["timeout"], 600)  # timeout kwarg
