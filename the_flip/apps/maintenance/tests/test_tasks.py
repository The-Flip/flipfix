"""Tests for maintenance background tasks with mocking examples.

This file demonstrates mocking patterns for testing code that:
- Makes subprocess calls (ffmpeg)
- Makes HTTP requests
- Depends on environment variables/settings
- Has time-dependent behavior
"""

from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, tag

from the_flip.apps.core.test_utils import create_machine, create_staff_user
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia


@tag("tasks", "unit")
class TranscodeVideoJobTests(TestCase):
    """Tests for video transcoding task with mocked dependencies."""

    def setUp(self):
        """Set up test data."""
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
    def test_transcode_fails_without_config(self):
        """Transcode should fail when required env vars are missing."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        with self.assertRaises(ValueError) as context:
            transcode_video_job(self.media.id)

        self.assertIn("DJANGO_WEB_SERVICE_URL", str(context.exception))
        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)

    def test_transcode_skips_nonexistent_media(self):
        """Transcode should handle missing media gracefully."""
        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Should not raise, just log and return
        transcode_video_job(999999)  # Non-existent ID

    def test_transcode_skips_non_video_media(self):
        """Transcode should skip non-video media."""
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
    """Tests for error handling in video transcoding."""

    def setUp(self):
        """Set up test data."""
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
    def test_transcode_handles_ffmpeg_failure(self, mock_ffmpeg):
        """Transcode should set status to FAILED when ffmpeg fails."""
        import subprocess

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

    @patch("the_flip.apps.maintenance.tasks.DJANGO_WEB_SERVICE_URL", "http://test.com")
    @patch("the_flip.apps.maintenance.tasks.TRANSCODING_UPLOAD_TOKEN", "test-token")
    def test_transcode_handles_missing_file(self):
        """Transcode should fail gracefully when source file is missing."""
        import os

        from the_flip.apps.maintenance.tasks import transcode_video_job

        # Delete the source file before transcoding
        if os.path.exists(self.media.file.path):
            os.remove(self.media.file.path)

        with self.assertRaises(Exception):
            transcode_video_job(self.media.id)

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_FAILED)


@tag("tasks", "unit")
class EnqueueTranscodeTests(TestCase):
    """Tests for the enqueue_transcode function."""

    @patch("the_flip.apps.maintenance.tasks.async_task")
    def test_enqueue_calls_async_task(self, mock_async_task):
        """enqueue_transcode should call async_task with correct args."""
        from the_flip.apps.maintenance.tasks import enqueue_transcode

        enqueue_transcode(123)

        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][1], 123)  # media_id argument
        self.assertEqual(call_args[1]["timeout"], 600)  # timeout kwarg


@tag("tasks", "integration")
class SubprocessMockingExample(TestCase):
    """Example of mocking subprocess calls for ffmpeg tests.

    This demonstrates how to test code that calls ffmpeg without
    actually running ffmpeg.
    """

    @patch("subprocess.run")
    def test_ffmpeg_command_construction(self, mock_run):
        """Example: verify ffmpeg is called with correct arguments."""
        # Configure the mock to return a successful result
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ffmpeg version 6.0",
            stderr="",
        )

        # Your code that calls subprocess.run would go here
        # For example:
        import subprocess

        result = subprocess.run(
            ["ffmpeg", "-i", "input.mp4", "-c:v", "libx264", "output.mp4"],
            capture_output=True,
            text=True,
        )

        # Verify the mock was called
        mock_run.assert_called_once()

        # Verify specific arguments if needed
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "ffmpeg")
        self.assertIn("-c:v", call_args)
        self.assertIn("libx264", call_args)

    @patch("subprocess.run")
    def test_ffmpeg_error_handling(self, mock_run):
        """Example: test error handling when ffmpeg fails."""
        import subprocess

        # Configure mock to simulate ffmpeg failure
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg", "-i", "input.mp4"],
            stderr="Error: invalid input file",
        )

        # Test that your code handles the error correctly
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.run(
                ["ffmpeg", "-i", "input.mp4"],
                check=True,
                capture_output=True,
            )


@tag("tasks", "integration")
class HTTPRequestMockingExample(TestCase):
    """Example of mocking HTTP requests for API tests.

    This demonstrates how to test code that makes HTTP requests
    without actually making network calls.
    """

    @patch("requests.post")
    def test_successful_upload(self, mock_post):
        """Example: test successful HTTP upload."""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        import requests

        # Your upload code would go here
        response = requests.post(
            "https://example.com/upload",
            files={"video": ("test.mp4", b"content")},
            headers={"Authorization": "Bearer token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_upload_network_error(self, mock_post):
        """Example: test handling of network errors."""
        import requests

        # Simulate network error
        mock_post.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        with self.assertRaises(requests.exceptions.ConnectionError):
            requests.post("https://example.com/upload", data={})

    @patch("requests.post")
    def test_upload_timeout(self, mock_post):
        """Example: test handling of timeout errors."""
        import requests

        # Simulate timeout
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        with self.assertRaises(requests.exceptions.Timeout):
            requests.post("https://example.com/upload", data={}, timeout=5)


@tag("unit")
class SettingsOverrideExample(TestCase):
    """Example of overriding Django settings in tests."""

    @override_settings(RATE_LIMIT_REPORTS_PER_IP=1)
    def test_with_stricter_rate_limit(self):
        """Example: test with modified settings."""
        from django.conf import settings

        self.assertEqual(settings.RATE_LIMIT_REPORTS_PER_IP, 1)

    @override_settings(DEBUG=True, RATE_LIMIT_WINDOW_MINUTES=1)
    def test_multiple_settings_override(self):
        """Example: override multiple settings at once."""
        from django.conf import settings

        self.assertTrue(settings.DEBUG)
        self.assertEqual(settings.RATE_LIMIT_WINDOW_MINUTES, 1)


@tag("unit")
class TimeMockingExample(TestCase):
    """Example of mocking time-dependent behavior."""

    @patch("django.utils.timezone.now")
    def test_with_frozen_time(self, mock_now):
        """Example: test with a specific frozen time."""
        from datetime import datetime, timezone as dt_tz

        from django.utils import timezone

        # Set a specific time
        frozen_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=dt_tz.utc)
        mock_now.return_value = frozen_time

        # Your time-dependent code would go here
        current_time = timezone.now()

        self.assertEqual(current_time, frozen_time)
        self.assertEqual(current_time.year, 2024)
        self.assertEqual(current_time.month, 6)
