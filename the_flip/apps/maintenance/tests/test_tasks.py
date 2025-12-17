"""Tests for maintenance background tasks."""

import logging
import subprocess
import tempfile
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from the_flip.apps.core.test_utils import TemporaryMediaMixin, create_machine
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia


@tag("tasks", "unit")
class GetTranscodingConfigTests(TestCase):
    """Tests for _get_transcoding_config helper."""

    def test_returns_values_when_both_configured(self):
        """Returns tuple of (url, token) when both are provided."""
        from the_flip.apps.core.tasks import _get_transcoding_config

        url, token = _get_transcoding_config(
            web_service_url="https://example.com",
            upload_token="secret-token",
        )
        self.assertEqual(url, "https://example.com")
        self.assertEqual(token, "secret-token")

    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", None)
    def test_raises_when_url_missing(self):
        """Raises ValueError when web_service_url is not configured."""
        from the_flip.apps.core.tasks import _get_transcoding_config

        with self.assertRaises(ValueError) as context:
            _get_transcoding_config(web_service_url=None, upload_token="token")

        self.assertIn("DJANGO_WEB_SERVICE_URL", str(context.exception))

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", None)
    def test_raises_when_token_missing(self):
        """Raises ValueError when upload_token is not configured."""
        from the_flip.apps.core.tasks import _get_transcoding_config

        with self.assertRaises(ValueError) as context:
            _get_transcoding_config(web_service_url="https://example.com", upload_token=None)

        self.assertIn("TRANSCODING_UPLOAD_TOKEN", str(context.exception))

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", None)
    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", None)
    def test_raises_when_both_missing(self):
        """Raises ValueError listing both missing vars when neither configured."""
        from the_flip.apps.core.tasks import _get_transcoding_config

        with self.assertRaises(ValueError) as context:
            _get_transcoding_config(web_service_url=None, upload_token=None)

        error_msg = str(context.exception)
        self.assertIn("DJANGO_WEB_SERVICE_URL", error_msg)
        self.assertIn("TRANSCODING_UPLOAD_TOKEN", error_msg)

    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", "https://env-url.com")
    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", "env-token")
    def test_falls_back_to_env_vars(self):
        """Uses module-level env vars when parameters are None."""
        from the_flip.apps.core.tasks import _get_transcoding_config

        url, token = _get_transcoding_config()
        self.assertEqual(url, "https://env-url.com")
        self.assertEqual(token, "env-token")


@tag("tasks", "unit")
class SleepWithBackoffTests(TestCase):
    """Tests for _sleep_with_backoff helper."""

    @patch("the_flip.apps.core.tasks.time.sleep")
    def test_sleeps_with_exponential_backoff(self, mock_sleep):
        """Sleeps with exponential backoff (2^attempt seconds)."""
        from the_flip.apps.core.tasks import _sleep_with_backoff

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        _sleep_with_backoff(attempt=1, max_retries=3, error_detail="test")
        mock_sleep.assert_called_with(2)

        mock_sleep.reset_mock()
        _sleep_with_backoff(attempt=2, max_retries=3, error_detail="test")
        mock_sleep.assert_called_with(4)

        mock_sleep.reset_mock()
        _sleep_with_backoff(attempt=3, max_retries=5, error_detail="test")
        mock_sleep.assert_called_with(8)

    def test_raises_when_retries_exhausted(self):
        """Raises exception when attempt equals max_retries."""
        from the_flip.apps.core.tasks import _sleep_with_backoff

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        with self.assertRaises(Exception) as context:
            _sleep_with_backoff(attempt=3, max_retries=3, error_detail="connection refused")

        self.assertIn("3 attempts", str(context.exception))
        self.assertIn("connection refused", str(context.exception))


@tag("tasks", "unit")
class UploadTranscodedFilesTests(TestCase):
    """Tests for _upload_transcoded_files helper."""

    def setUp(self):
        super().setUp()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        # Create temp files to simulate transcoded video and poster
        self.video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.video_file.write(b"fake video content")
        self.video_file.close()

        self.poster_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        self.poster_file.write(b"fake poster content")
        self.poster_file.close()

    def tearDown(self):
        import os

        for f in (self.video_file, self.poster_file):
            if os.path.exists(f.name):
                os.unlink(f.name)
        super().tearDown()

    @patch("the_flip.apps.core.tasks.requests.post")
    def test_upload_succeeds_on_first_attempt(self, mock_post):
        """Upload succeeds immediately when server returns 200."""
        from the_flip.apps.core.tasks import _upload_transcoded_files

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Upload successful"}
        mock_post.return_value = mock_response

        _upload_transcoded_files(
            media_id=123,
            video_path=self.video_file.name,
            poster_path=self.poster_file.name,
            web_service_url="https://example.com",
            upload_token="secret-token",
        )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(call_kwargs["timeout"], 300)

        # Verify payload contains required fields
        data = call_kwargs["data"]
        self.assertEqual(data["media_id"], "123")
        self.assertEqual(data["model_name"], "LogEntryMedia")
        self.assertEqual(data["log_entry_media_id"], "123")  # Legacy field

    @patch("the_flip.apps.core.tasks.time.sleep")
    @patch("the_flip.apps.core.tasks.requests.post")
    def test_upload_retries_on_server_error(self, mock_post, mock_sleep):
        """Upload retries with backoff when server returns 500."""
        from the_flip.apps.core.tasks import _upload_transcoded_files

        # First two attempts fail with 500, third succeeds
        fail_response = Mock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"message": "Upload successful"}

        mock_post.side_effect = [fail_response, fail_response, success_response]

        _upload_transcoded_files(
            media_id=123,
            video_path=self.video_file.name,
            poster_path=self.poster_file.name,
            web_service_url="https://example.com",
            upload_token="secret-token",
            max_retries=3,
        )

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("the_flip.apps.core.tasks.time.sleep")
    @patch("the_flip.apps.core.tasks.requests.post")
    def test_upload_retries_on_connection_error(self, mock_post, mock_sleep):
        """Upload retries with backoff on connection errors."""
        import requests

        from the_flip.apps.core.tasks import _upload_transcoded_files

        # First attempt fails with connection error, second succeeds
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"message": "Upload successful"}

        mock_post.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            success_response,
        ]

        _upload_transcoded_files(
            media_id=123,
            video_path=self.video_file.name,
            poster_path=self.poster_file.name,
            web_service_url="https://example.com",
            upload_token="secret-token",
            max_retries=3,
        )

        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(2)

    @patch("the_flip.apps.core.tasks.time.sleep")
    @patch("the_flip.apps.core.tasks.requests.post")
    def test_upload_raises_after_max_retries(self, mock_post, mock_sleep):
        """Upload raises exception after exhausting all retries."""
        from the_flip.apps.core.tasks import _upload_transcoded_files

        fail_response = Mock()
        fail_response.status_code = 503
        fail_response.text = "Service Unavailable"
        mock_post.return_value = fail_response

        with self.assertRaises(Exception) as context:
            _upload_transcoded_files(
                media_id=123,
                video_path=self.video_file.name,
                poster_path=self.poster_file.name,
                web_service_url="https://example.com",
                upload_token="secret-token",
                max_retries=3,
            )

        self.assertIn("3 attempts", str(context.exception))
        self.assertEqual(mock_post.call_count, 3)


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

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", "https://example.com")
    def test_transcode_success_path(self):
        """Task runs probe, ffmpeg, and upload on success."""
        from the_flip.apps.core.tasks import transcode_video_job

        probe = Mock(return_value=120)
        run_ffmpeg = Mock()
        upload = Mock()

        transcode_video_job(
            self.media.id,
            "LogEntryMedia",
            probe=probe,
            run_ffmpeg=run_ffmpeg,
            upload=upload,
        )

        # Probe called once to get duration
        probe.assert_called_once()

        # FFmpeg called twice: once for video transcode, once for poster
        self.assertEqual(run_ffmpeg.call_count, 2)

        # Upload called with media_id and temp file paths
        upload.assert_called_once()
        call_args = upload.call_args
        self.assertEqual(call_args[0][0], self.media.id)
        self.assertIn(".mp4", call_args[0][1])  # video path
        self.assertIn(".jpg", call_args[0][2])  # poster path

        # Duration saved to media, status still PROCESSING (upload endpoint sets READY)
        self.media.refresh_from_db()
        self.assertEqual(self.media.duration, 120)
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_PROCESSING)

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", "https://example.com")
    def test_transcode_sets_processing_status_before_work(self):
        """Task sets status to PROCESSING before starting transcode."""
        from the_flip.apps.core.tasks import transcode_video_job

        statuses_during_run = []

        def capture_status_on_ffmpeg(*args):
            # Read status from DB during ffmpeg run
            self.media.refresh_from_db()
            statuses_during_run.append(self.media.transcode_status)

        probe = Mock(return_value=120)
        run_ffmpeg = Mock(side_effect=capture_status_on_ffmpeg)
        upload = Mock()

        transcode_video_job(
            self.media.id,
            "LogEntryMedia",
            probe=probe,
            run_ffmpeg=run_ffmpeg,
            upload=upload,
        )

        # Status was PROCESSING during ffmpeg execution
        self.assertEqual(statuses_during_run[0], LogEntryMedia.STATUS_PROCESSING)


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

    @patch("the_flip.apps.core.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    @patch("the_flip.apps.core.tasks.DJANGO_WEB_SERVICE_URL", "https://example.com")
    def test_transcode_sets_failed_status_when_upload_errors(self):
        """Task sets status to FAILED when upload raises an exception."""
        from the_flip.apps.core.tasks import transcode_video_job

        probe = Mock(return_value=120)
        run_ffmpeg = Mock()
        upload = Mock(side_effect=RuntimeError("Upload failed after 3 attempts"))

        with self.assertRaises(RuntimeError):
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
        self.assertEqual(run_ffmpeg.call_count, 2)
        upload.assert_called_once()


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
