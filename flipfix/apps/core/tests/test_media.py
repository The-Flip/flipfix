"""Tests for core media utilities."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from flipfix.apps.core.media import ALLOWED_MEDIA_EXTENSIONS, ALLOWED_PHOTO_EXTENSIONS
from flipfix.apps.core.media_upload import attach_media_files
from flipfix.apps.core.test_utils import (
    TemporaryMediaMixin,
    TestDataMixin,
    create_log_entry,
    create_part_request,
    create_part_request_update,
    create_problem_report,
)
from flipfix.apps.maintenance.models import LogEntryMedia, ProblemReportMedia
from flipfix.apps.parts.models import PartRequestMedia, PartRequestUpdateMedia


@tag("unit")
class MediaExtensionConfigTests(TestCase):
    """Tests for media extension configuration."""

    def test_avif_in_allowed_photo_extensions(self):
        """AVIF is in the allowed photo extensions set."""
        self.assertIn(".avif", ALLOWED_PHOTO_EXTENSIONS)

    def test_avif_in_allowed_media_extensions(self):
        """AVIF is in the allowed media extensions set."""
        self.assertIn(".avif", ALLOWED_MEDIA_EXTENSIONS)


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

    @patch("flipfix.apps.core.media_upload.enqueue_transcode")
    def test_attaches_video_and_enqueues_transcode(self, mock_enqueue):
        """Creates a video media record and enqueues transcoding."""
        video = SimpleUploadedFile("test.mp4", b"fake video", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[video],
                parent=self.log_entry,
                media_model=LogEntryMedia,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.VIDEO)
        self.assertEqual(result[0].transcode_status, LogEntryMedia.TranscodeStatus.PENDING)
        mock_enqueue.assert_called_once_with(media_id=result[0].id, model_name="LogEntryMedia")

    @patch("flipfix.apps.core.media_upload.enqueue_transcode")
    def test_photo_does_not_enqueue_transcode(self, mock_enqueue):
        """Photo uploads should not trigger transcoding."""
        photo = SimpleUploadedFile("test.jpg", b"fake jpg", content_type="image/jpeg")

        with self.captureOnCommitCallbacks(execute=True):
            attach_media_files(
                media_files=[photo],
                parent=self.log_entry,
                media_model=LogEntryMedia,
            )

        mock_enqueue.assert_not_called()

    @patch("flipfix.apps.core.media_upload.enqueue_transcode")
    def test_handles_mixed_uploads(self, mock_enqueue):
        """Handles a mix of photos and videos in one call."""
        photo = SimpleUploadedFile("pic.jpg", b"fake jpg", content_type="image/jpeg")
        video = SimpleUploadedFile("clip.mp4", b"fake video", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[photo, video],
                parent=self.log_entry,
                media_model=LogEntryMedia,
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

    @patch("flipfix.apps.core.media_upload.enqueue_transcode")
    def test_detects_video_by_extension(self, mock_enqueue):
        """Detects video files by extension even without video content type."""
        # .webm file with generic content type
        webm = SimpleUploadedFile(
            "clip.webm", b"fake webm", content_type="application/octet-stream"
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = attach_media_files(
                media_files=[webm],
                parent=self.log_entry,
                media_model=LogEntryMedia,
            )

        self.assertEqual(result[0].media_type, LogEntryMedia.MediaType.VIDEO)
        mock_enqueue.assert_called_once()


@tag("models")
class AbstractMediaStrTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for AbstractMedia.__str__ across all concrete subclasses."""

    def test_log_entry_media_str(self):
        """LogEntryMedia.__str__ includes media type and parent ID."""
        log_entry = create_log_entry(machine=self.machine, text="Test")
        media = LogEntryMedia.objects.create(
            log_entry=log_entry,
            media_type=LogEntryMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(str(media), f"Photo for log entry {log_entry.pk}")

    def test_problem_report_media_str(self):
        """ProblemReportMedia.__str__ includes media type and parent ID."""
        report = create_problem_report(machine=self.machine)
        media = ProblemReportMedia.objects.create(
            problem_report=report,
            media_type=ProblemReportMedia.MediaType.VIDEO,
            file=SimpleUploadedFile("test.mp4", b"fake", content_type="video/mp4"),
        )
        self.assertEqual(str(media), f"Video for problem report {report.pk}")

    def test_part_request_media_str(self):
        """PartRequestMedia.__str__ includes media type and parent ID."""
        part_request = create_part_request(machine=self.machine)
        media = PartRequestMedia.objects.create(
            part_request=part_request,
            media_type=PartRequestMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(str(media), f"Photo for part request {part_request.pk}")

    def test_part_request_update_media_str(self):
        """PartRequestUpdateMedia.__str__ includes media type and parent ID."""
        update = create_part_request_update()
        media = PartRequestUpdateMedia.objects.create(
            update=update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(str(media), f"Photo for update {update.pk}")


@tag("models")
class AbstractMediaAdminHistoryUrlTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for AbstractMedia.get_admin_history_url across all concrete subclasses."""

    def test_log_entry_media_admin_history_url(self):
        """LogEntryMedia returns correct admin history URL."""
        log_entry = create_log_entry(machine=self.machine, text="Test")
        media = LogEntryMedia.objects.create(
            log_entry=log_entry,
            media_type=LogEntryMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(
            media.get_admin_history_url(),
            f"/admin/maintenance/logentrymedia/{media.pk}/history/",
        )

    def test_problem_report_media_admin_history_url(self):
        """ProblemReportMedia returns correct admin history URL."""
        report = create_problem_report(machine=self.machine)
        media = ProblemReportMedia.objects.create(
            problem_report=report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(
            media.get_admin_history_url(),
            f"/admin/maintenance/problemreportmedia/{media.pk}/history/",
        )

    def test_part_request_media_admin_history_url(self):
        """PartRequestMedia returns correct admin history URL."""
        part_request = create_part_request(machine=self.machine)
        media = PartRequestMedia.objects.create(
            part_request=part_request,
            media_type=PartRequestMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(
            media.get_admin_history_url(),
            f"/admin/parts/partrequestmedia/{media.pk}/history/",
        )

    def test_part_request_update_media_admin_history_url(self):
        """PartRequestUpdateMedia returns correct admin history URL."""
        update = create_part_request_update()
        media = PartRequestUpdateMedia.objects.create(
            update=update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
        )
        self.assertEqual(
            media.get_admin_history_url(),
            f"/admin/parts/partrequestupdatemedia/{media.pk}/history/",
        )
