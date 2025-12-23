"""Tests for log entry media upload functionality."""

from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from the_flip.apps.core.test_utils import DATETIME_INPUT_FORMAT, TestDataMixin
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia


@tag("views", "ajax", "media")
class LogEntryVideoUploadTests(TestDataMixin, TestCase):
    """Tests for video upload via AJAX on log entry creation."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def _create_log_entry_and_get_detail_url(self):
        """Create a log entry via POST and return its detail URL."""
        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Test entry",
            },
        )
        self.assertEqual(response.status_code, 302, "Log entry creation should redirect on success")
        log_entry = LogEntry.objects.get()  # Fails if != 1 entry exists
        return reverse("log-detail", kwargs={"pk": log_entry.pk})

    @patch("the_flip.apps.core.mixins.enqueue_transcode")
    def test_ajax_video_upload_enqueues_transcode_with_model_name(self, mock_enqueue):
        """AJAX video upload should call enqueue_transcode with correct model_name.

        This test verifies that when a video is uploaded via AJAX, the view
        correctly calls enqueue_transcode with both media_id and model_name.
        This prevents regressions like missing the model_name argument.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.maintainer_user)
        detail_url = self._create_log_entry_and_get_detail_url()

        # Upload a video via AJAX (must have video content_type for detection)
        video_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")

        # Use COMMIT_ON_SUCCESS to trigger on_commit callbacks in TestCase
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                detail_url,
                {
                    "action": "upload_media",
                    "media_file": video_file,
                },
            )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["media_type"], "video")

        # Verify enqueue_transcode was called with correct arguments
        media = LogEntryMedia.objects.first()
        mock_enqueue.assert_called_once_with(media_id=media.id, model_name="LogEntryMedia")

    @patch("the_flip.apps.maintenance.views.log_entries.enqueue_transcode")
    def test_form_video_upload_enqueues_transcode_with_model_name(self, mock_enqueue):
        """Video uploaded via form submission should call enqueue_transcode correctly.

        This tests the form submission path (MachineLogCreateView.form_valid) which is
        separate from the AJAX upload path tested above. Both paths call enqueue_transcode
        but in different code locations.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.maintainer_user)

        video_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.create_url,
                {
                    "work_date": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                    "submitter_name": "Test User",
                    "text": "Test entry with video",
                    "media_file": video_file,
                },
            )

        self.assertEqual(response.status_code, 302)

        # Verify enqueue_transcode was called with correct arguments
        media = LogEntryMedia.objects.first()
        self.assertIsNotNone(media)
        mock_enqueue.assert_called_once_with(media_id=media.id, model_name="LogEntryMedia")

    @patch("the_flip.apps.core.mixins.enqueue_transcode")
    def test_ajax_photo_upload_does_not_enqueue_transcode(self, mock_enqueue):
        """AJAX photo upload should NOT trigger video transcoding."""
        self.client.force_login(self.maintainer_user)
        detail_url = self._create_log_entry_and_get_detail_url()

        # Create a real image file
        img = Image.new("RGB", (100, 100), color="blue")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        img_io.name = "test.png"

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                detail_url,
                {
                    "action": "upload_media",
                    "media_file": img_io,
                },
            )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["media_type"], "photo")

        # Verify enqueue_transcode was NOT called for photos
        mock_enqueue.assert_not_called()
