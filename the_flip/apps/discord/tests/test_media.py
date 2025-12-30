"""Tests for Discord media download and attachment functionality."""

from unittest.mock import AsyncMock, MagicMock

from django.test import TestCase, override_settings, tag

from the_flip.apps.core.media import ALLOWED_MEDIA_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
from the_flip.apps.core.test_utils import (
    TemporaryMediaMixin,
    create_machine,
    create_maintainer_user,
)
from the_flip.apps.discord.context import (
    ContextMessage,
    _filter_supported_attachments,
)
from the_flip.apps.discord.media import (
    _dedupe_by_url,
    _get_media_class_and_parent_field,
    _is_video,
)
from the_flip.apps.maintenance.models import (
    LogEntry,
    LogEntryMedia,
    ProblemReport,
    ProblemReportMedia,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


def _make_mock_attachment(
    filename: str, url: str | None = None, content_type: str | None = None
) -> MagicMock:
    """Create a mock Discord attachment."""
    attachment = MagicMock()
    attachment.filename = filename
    attachment.url = url or f"https://cdn.discordapp.com/attachments/12345/{filename}"
    attachment.content_type = content_type or "image/jpeg"
    return attachment


@tag("discord")
class AllowedMediaExtensionsTests(TestCase):
    """Tests for ALLOWED_MEDIA_EXTENSIONS constant."""

    def test_includes_common_photo_formats(self):
        """Includes common photo formats."""
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            self.assertIn(ext, ALLOWED_MEDIA_EXTENSIONS, f"{ext} should be supported")

    def test_includes_heic_heif(self):
        """Includes HEIC/HEIF formats (iPhone photos)."""
        self.assertIn(".heic", ALLOWED_MEDIA_EXTENSIONS)
        self.assertIn(".heif", ALLOWED_MEDIA_EXTENSIONS)

    def test_includes_video_formats(self):
        """Includes video formats."""
        for ext in [".mp4", ".mov", ".m4v", ".webm"]:
            self.assertIn(ext, ALLOWED_MEDIA_EXTENSIONS, f"{ext} should be supported")

    def test_excludes_unsupported_formats(self):
        """Excludes unsupported formats."""
        for ext in [".pdf", ".doc", ".docx", ".txt", ".zip", ".exe"]:
            self.assertNotIn(ext, ALLOWED_MEDIA_EXTENSIONS, f"{ext} should not be supported")


@tag("discord")
class FilterSupportedAttachmentsTests(TestCase):
    """Tests for _filter_supported_attachments()."""

    def test_filters_to_supported_only(self):
        """Only returns attachments with supported extensions."""
        attachments = [
            _make_mock_attachment("photo.jpg"),
            _make_mock_attachment("document.pdf"),
            _make_mock_attachment("video.mp4"),
            _make_mock_attachment("readme.txt"),
        ]

        result = _filter_supported_attachments(attachments)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].filename, "photo.jpg")
        self.assertEqual(result[1].filename, "video.mp4")

    def test_case_insensitive_extension(self):
        """Extension matching is case-insensitive."""
        attachments = [
            _make_mock_attachment("photo.JPG"),
            _make_mock_attachment("photo.Png"),
            _make_mock_attachment("video.MP4"),
        ]

        result = _filter_supported_attachments(attachments)

        self.assertEqual(len(result), 3)

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        result = _filter_supported_attachments([])
        self.assertEqual(result, [])

    def test_no_supported_returns_empty(self):
        """Returns empty list when no supported formats found."""
        attachments = [
            _make_mock_attachment("doc.pdf"),
            _make_mock_attachment("archive.zip"),
        ]

        result = _filter_supported_attachments(attachments)

        self.assertEqual(result, [])


@tag("discord")
class IsVideoTests(TestCase):
    """Tests for _is_video() helper."""

    def test_recognizes_video_extensions(self):
        """Recognizes video file extensions."""
        for ext in ALLOWED_VIDEO_EXTENSIONS:
            self.assertTrue(_is_video(f"test{ext}"), f"{ext} should be recognized as video")

    def test_recognizes_uppercase_video(self):
        """Recognizes uppercase video extensions."""
        self.assertTrue(_is_video("test.MP4"))
        self.assertTrue(_is_video("test.MOV"))

    def test_rejects_photo_extensions(self):
        """Rejects photo file extensions."""
        self.assertFalse(_is_video("test.jpg"))
        self.assertFalse(_is_video("test.png"))
        self.assertFalse(_is_video("test.heic"))


@tag("discord")
class DedupeByUrlTests(TestCase):
    """Tests for _dedupe_by_url() helper."""

    def test_removes_duplicate_urls(self):
        """Removes attachments with duplicate URLs."""
        url = "https://cdn.discordapp.com/attachments/12345/photo.jpg"
        attachments = [
            _make_mock_attachment("photo.jpg", url=url),
            _make_mock_attachment("photo.jpg", url=url),  # Same URL
        ]

        result = _dedupe_by_url(attachments)

        self.assertEqual(len(result), 1)

    def test_preserves_different_urls(self):
        """Preserves attachments with different URLs."""
        attachments = [
            _make_mock_attachment("photo1.jpg", url="https://cdn.discordapp.com/1/photo.jpg"),
            _make_mock_attachment("photo2.jpg", url="https://cdn.discordapp.com/2/photo.jpg"),
        ]

        result = _dedupe_by_url(attachments)

        self.assertEqual(len(result), 2)

    def test_preserves_order(self):
        """Preserves order, keeping first occurrence."""
        attachments = [
            _make_mock_attachment("first.jpg", url="https://cdn.discordapp.com/1/photo.jpg"),
            _make_mock_attachment("second.jpg", url="https://cdn.discordapp.com/2/photo.jpg"),
            _make_mock_attachment(
                "third.jpg", url="https://cdn.discordapp.com/1/photo.jpg"
            ),  # Dupe
        ]

        result = _dedupe_by_url(attachments)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].filename, "first.jpg")
        self.assertEqual(result[1].filename, "second.jpg")


@tag("discord")
class GetMediaClassAndParentFieldTests(TestCase):
    """Tests for _get_media_class_and_parent_field() helper."""

    def setUp(self):
        self.machine = create_machine()
        self.user = create_maintainer_user()
        self.maintainer = self.user.maintainer

    def test_log_entry(self):
        """Returns correct class for LogEntry."""
        log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test",
            maintainer_names="Test User",
        )

        media_class, parent_field, model_name = _get_media_class_and_parent_field(log_entry)

        self.assertEqual(media_class, LogEntryMedia)
        self.assertEqual(parent_field, "log_entry")
        self.assertEqual(model_name, "LogEntryMedia")

    def test_problem_report(self):
        """Returns correct class for ProblemReport."""
        problem_report = ProblemReport.objects.create(
            machine=self.machine,
            description="Test",
            problem_type=ProblemReport.ProblemType.OTHER,
        )

        media_class, parent_field, model_name = _get_media_class_and_parent_field(problem_report)

        self.assertEqual(media_class, ProblemReportMedia)
        self.assertEqual(parent_field, "problem_report")
        self.assertEqual(model_name, "ProblemReportMedia")

    def test_part_request(self):
        """Returns correct class for PartRequest."""
        part_request = PartRequest.objects.create(
            text="Test",
            requested_by=self.maintainer,
        )

        media_class, parent_field, model_name = _get_media_class_and_parent_field(part_request)

        self.assertEqual(media_class, PartRequestMedia)
        self.assertEqual(parent_field, "part_request")
        self.assertEqual(model_name, "PartRequestMedia")

    def test_part_request_update(self):
        """Returns correct class for PartRequestUpdate."""
        part_request = PartRequest.objects.create(
            text="Test",
            requested_by=self.maintainer,
        )
        update = PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Update",
            posted_by=self.maintainer,
        )

        media_class, parent_field, model_name = _get_media_class_and_parent_field(update)

        self.assertEqual(media_class, PartRequestUpdateMedia)
        self.assertEqual(parent_field, "update")
        self.assertEqual(model_name, "PartRequestUpdateMedia")


@tag("discord")
class ContextMessageAttachmentsTests(TestCase):
    """Tests for ContextMessage.attachments field."""

    def test_has_attachments_field(self):
        """ContextMessage has attachments field."""
        msg = ContextMessage(
            id="123",
            author="test",
            content="test",
            timestamp="2025-01-01T00:00:00Z",
        )

        # Field should exist and default to empty list
        self.assertEqual(msg.attachments, [])

    def test_can_store_attachments(self):
        """Can store attachments in ContextMessage."""
        attachments = [_make_mock_attachment("photo.jpg")]
        msg = ContextMessage(
            id="123",
            author="test",
            content="test",
            timestamp="2025-01-01T00:00:00Z",
            attachments=attachments,
        )

        self.assertEqual(len(msg.attachments), 1)
        self.assertEqual(msg.attachments[0].filename, "photo.jpg")


@tag("discord")
@override_settings(SITE_URL="https://flipfix.example.com")
class DownloadAndCreateMediaTests(TemporaryMediaMixin, TestCase):
    """Tests for download_and_create_media()."""

    def setUp(self):
        super().setUp()
        self.machine = create_machine()
        self.user = create_maintainer_user()
        self.maintainer = self.user.maintainer

    async def test_downloads_and_creates_photo_media(self):
        """Downloads attachment and creates photo media record."""
        from asgiref.sync import sync_to_async

        from the_flip.apps.discord.media import download_and_create_media

        log_entry = await self._create_log_entry()

        # Create mock attachment that returns image data
        attachment = _make_mock_attachment("photo.jpg", content_type="image/jpeg")
        attachment.read = AsyncMock(return_value=self._create_test_image_bytes())

        success, failed = await download_and_create_media(log_entry, [attachment])

        self.assertEqual(success, 1)
        self.assertEqual(failed, 0)

        # Verify media record was created
        await sync_to_async(log_entry.refresh_from_db)()
        media_count = await sync_to_async(log_entry.media.count)()
        self.assertEqual(media_count, 1)
        media = await sync_to_async(log_entry.media.first)()
        self.assertEqual(media.media_type, LogEntryMedia.MediaType.PHOTO)

    async def test_handles_download_failure(self):
        """Handles download failures gracefully."""
        from asgiref.sync import sync_to_async

        from the_flip.apps.discord.media import download_and_create_media

        log_entry = await self._create_log_entry()

        # Create mock attachment that raises on read
        attachment = _make_mock_attachment("photo.jpg")
        attachment.read = AsyncMock(side_effect=Exception("Download failed"))

        success, failed = await download_and_create_media(log_entry, [attachment])

        self.assertEqual(success, 0)
        self.assertEqual(failed, 1)

        # No media should be created
        await sync_to_async(log_entry.refresh_from_db)()
        media_count = await sync_to_async(log_entry.media.count)()
        self.assertEqual(media_count, 0)

    async def test_dedupes_by_url(self):
        """Deduplicates attachments with same URL."""
        from asgiref.sync import sync_to_async

        from the_flip.apps.discord.media import download_and_create_media

        log_entry = await self._create_log_entry()

        url = "https://cdn.discordapp.com/attachments/123/photo.jpg"
        attachment1 = _make_mock_attachment("photo.jpg", url=url)
        attachment1.read = AsyncMock(return_value=self._create_test_image_bytes())
        attachment2 = _make_mock_attachment("photo.jpg", url=url)  # Same URL
        attachment2.read = AsyncMock(return_value=self._create_test_image_bytes())

        success, failed = await download_and_create_media(log_entry, [attachment1, attachment2])

        self.assertEqual(success, 1)  # Only one download despite two attachments
        self.assertEqual(failed, 0)
        media_count = await sync_to_async(log_entry.media.count)()
        self.assertEqual(media_count, 1)

    async def test_empty_attachments_returns_zero(self):
        """Empty attachment list returns zero counts."""
        from the_flip.apps.discord.media import download_and_create_media

        log_entry = await self._create_log_entry()

        success, failed = await download_and_create_media(log_entry, [])

        self.assertEqual(success, 0)
        self.assertEqual(failed, 0)

    async def test_video_creates_media_with_pending_status(self):
        """Video attachments create media record with PENDING transcode status."""
        from asgiref.sync import sync_to_async

        from the_flip.apps.discord.media import download_and_create_media

        log_entry = await self._create_log_entry()

        attachment = _make_mock_attachment("video.mp4", content_type="video/mp4")
        attachment.read = AsyncMock(return_value=b"fake video data")

        success, failed = await download_and_create_media(log_entry, [attachment])

        self.assertEqual(success, 1)
        self.assertEqual(failed, 0)

        # Verify media record was created with correct type and status
        await sync_to_async(log_entry.refresh_from_db)()
        media = await sync_to_async(log_entry.media.first)()
        self.assertEqual(media.media_type, LogEntryMedia.MediaType.VIDEO)
        self.assertEqual(media.transcode_status, LogEntryMedia.TranscodeStatus.PENDING)
        # Note: on_commit callbacks don't fire during tests (transaction is rolled back),
        # so we verify the status is PENDING rather than checking enqueue_transcode was called

    # Helper methods

    async def _create_log_entry(self) -> LogEntry:
        """Create a test log entry."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create():
            return LogEntry.objects.create(
                machine=self.machine,
                text="Test log entry",
                maintainer_names="Test User",
            )

        return await create()

    def _create_test_image_bytes(self) -> bytes:
        """Create minimal valid JPEG bytes."""
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        return buffer.getvalue()
