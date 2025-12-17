"""Tests for maintenance background tasks."""

import logging
import subprocess
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from the_flip.apps.core.test_utils import TemporaryMediaMixin, create_machine
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia


class VideoMediaTestMixin:
    """
    Mixin providing video media test fixtures.

    Provides: self.machine, self.log_entry, self.media (video with pending status)

    Usage:
        class MyTests(VideoMediaTestMixin, TemporaryMediaMixin, TestCase):
            def test_something(self):
                # self.media is a LogEntryMedia with TYPE_VIDEO
    """

    def setUp(self):
        super().setUp()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.machine = create_machine()
        self.log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test entry with video",
        )
        video_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_VIDEO,
            file=video_file,
            transcode_status=LogEntryMedia.STATUS_PENDING,
        )


@tag("tasks", "unit")
class TranscodeVideoJobTests(VideoMediaTestMixin, TemporaryMediaMixin, TestCase):
    """Tests for transcode_video_job task."""

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", None)
    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", None)
    def test_transcode_raises_without_required_config(self):
        """Task raises ValueError when DJANGO_WEB_SERVICE_URL is not configured."""
        from the_flip.apps.core.tasks import transcode_video_job

        probe = Mock(return_value=120)
        run_ffmpeg = Mock()
        upload = Mock()

        with self.assertRaises(ValueError) as context:
            transcode_video_job(
                self.media.id,
                "LogEntryMedia",
                probe=probe,
                run_ffmpeg=run_ffmpeg,
                upload=upload,
            )

        self.assertIn("DJANGO_WEB_SERVICE_URL", str(context.exception))
        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        probe.assert_not_called()
        run_ffmpeg.assert_not_called()
        upload.assert_not_called()

    def test_transcode_skips_nonexistent_media(self):
        """Task silently skips non-existent media IDs."""
        from the_flip.apps.core.tasks import transcode_video_job

        # Should not raise, just log and return
        transcode_video_job(999999, "LogEntryMedia")  # Non-existent ID

    def test_transcode_skips_non_video_media(self):
        """Task skips non-video media types without processing."""
        from the_flip.apps.core.tasks import transcode_video_job

        # Change media type to photo
        self.media.media_type = LogEntryMedia.TYPE_PHOTO
        self.media.save()

        # Should not process, just return
        transcode_video_job(self.media.id, "LogEntryMedia")
        self.media.refresh_from_db()
        # Status should remain pending (not changed)
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_PENDING)


@tag("tasks", "unit")
class TranscodeVideoErrorHandlingTests(VideoMediaTestMixin, TemporaryMediaMixin, TestCase):
    """Tests for transcode error handling."""

    def test_transcode_sets_failed_status_when_ffmpeg_errors(self):
        """Task sets status to FAILED when ffmpeg exits with error."""
        from the_flip.apps.core.tasks import transcode_video_job

        probe = Mock(return_value=120)
        upload = Mock()
        run_ffmpeg = Mock()
        # Simulate ffmpeg failing with non-zero exit code
        run_ffmpeg.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg", "-i", "input.mp4"],
            stderr="Error: corrupt input file",
        )

        with self.assertRaises(subprocess.CalledProcessError):
            transcode_video_job(
                self.media.id,
                "LogEntryMedia",
                probe=probe,
                run_ffmpeg=run_ffmpeg,
                upload=upload,
            )

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        probe.assert_called_once()
        upload.assert_not_called()

    def test_transcode_fails_when_source_file_missing(self):
        """Task sets status to FAILED when source file cannot be read."""
        from the_flip.apps.core.tasks import transcode_video_job

        probe = Mock(return_value=120)
        upload = Mock()
        run_ffmpeg = Mock()
        # Simulate ffmpeg failing when reading input (e.g., missing file)
        run_ffmpeg.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg", "-i", str(self.media.file.path)],
            stderr="No such file or directory",
        )

        with self.assertRaises(subprocess.CalledProcessError):
            transcode_video_job(
                self.media.id,
                "LogEntryMedia",
                probe=probe,
                run_ffmpeg=run_ffmpeg,
                upload=upload,
            )

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)
        probe.assert_called_once()
        upload.assert_not_called()


@tag("tasks", "unit")
class EnqueueTranscodeTests(TemporaryMediaMixin, TestCase):
    """Tests for enqueue_transcode helper."""

    def test_enqueue_transcode_invokes_async_task_with_media_id(self):
        """enqueue_transcode schedules async task with correct parameters."""
        from the_flip.apps.core.tasks import enqueue_transcode

        async_runner = Mock()
        enqueue_transcode(123, "LogEntryMedia", async_runner=async_runner)

        async_runner.assert_called_once()
        call_args = async_runner.call_args
        self.assertEqual(call_args[0][1], 123)  # media_id argument
        self.assertEqual(call_args[0][2], "LogEntryMedia")  # model_name argument
        self.assertEqual(call_args[1]["timeout"], 600)  # timeout kwarg
