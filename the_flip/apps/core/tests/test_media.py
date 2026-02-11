"""Tests for core media utilities."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from the_flip.apps.core.media import attach_media_files
from the_flip.apps.core.test_utils import TestDataMixin, create_log_entry
from the_flip.apps.maintenance.models import LogEntryMedia


@tag("models")
class AttachMediaFilesTests(TestDataMixin, TestCase):
    """Tests for the attach_media_files utility."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test")

    def test_attaches_photo(self):
        """Creates a photo media record for an image upload."""
        photo = SimpleUploadedFile("test.png", b"fake png", content_type="image/png")

        result = attach_media_files(
            media_files=[photo], parent=self.log_entry, media_model=LogEntryMedia
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.PHOTO)
        self.assertEqual(result[0].log_entry, self.log_entry)
        self.assertEqual(result[0].transcode_status, "")

    @patch("the_flip.apps.core.media.enqueue_transcode")
    def test_attaches_video_and_enqueues_transcode(self, mock_enqueue):
        """Creates a video media record and enqueues transcoding."""
        video = SimpleUploadedFile("test.mp4", b"fake video", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[video], parent=self.log_entry, media_model=LogEntryMedia
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.VIDEO)
        self.assertEqual(result[0].transcode_status, LogEntryMedia.TranscodeStatus.PENDING)
        mock_enqueue.assert_called_once_with(media_id=result[0].id, model_name="LogEntryMedia")

    @patch("the_flip.apps.core.media.enqueue_transcode")
    def test_photo_does_not_enqueue_transcode(self, mock_enqueue):
        """Photo uploads should not trigger video transcoding."""
        photo = SimpleUploadedFile("test.jpg", b"fake jpg", content_type="image/jpeg")

        with self.captureOnCommitCallbacks(execute=True):
            attach_media_files(
                media_files=[photo], parent=self.log_entry, media_model=LogEntryMedia
            )

        mock_enqueue.assert_not_called()

    @patch("the_flip.apps.core.media.enqueue_transcode")
    def test_handles_mixed_uploads(self, mock_enqueue):
        """Handles a mix of photos and videos in one call."""
        photo = SimpleUploadedFile("pic.jpg", b"fake jpg", content_type="image/jpeg")
        video = SimpleUploadedFile("clip.mp4", b"fake video", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[photo, video], parent=self.log_entry, media_model=LogEntryMedia
            )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.PHOTO)
        self.assertEqual(result[1].media_type, LogEntryMedia.MediaType.VIDEO)
        mock_enqueue.assert_called_once()

    def test_empty_list_creates_nothing(self):
        """An empty file list creates no media records."""
        result = attach_media_files(
            media_files=[], parent=self.log_entry, media_model=LogEntryMedia
        )

        self.assertEqual(result, [])
        self.assertEqual(LogEntryMedia.objects.count(), 0)

    @patch("the_flip.apps.core.media.enqueue_transcode")
    def test_detects_video_by_extension(self, mock_enqueue):
        """Detects video files by extension even without video content type."""
        # .webm file with generic content type
        webm = SimpleUploadedFile(
            "clip.webm", b"fake webm", content_type="application/octet-stream"
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[webm], parent=self.log_entry, media_model=LogEntryMedia
            )

        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.VIDEO)
        mock_enqueue.assert_called_once()
