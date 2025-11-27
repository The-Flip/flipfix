"""Tests for maintenance app API endpoints."""

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_log_entry,
    create_shared_terminal,
    create_staff_user,
    create_user,
)
from the_flip.apps.maintenance.models import LogEntryMedia
from the_flip.apps.maintenance.utils import resize_image_file


@tag("api", "ajax")
class MaintainerAutocompleteViewTests(TestCase):
    """Tests for the maintainer autocomplete API endpoint."""

    def setUp(self):
        self.user1 = create_staff_user(username="alice", first_name="Alice", last_name="Smith")
        self.user2 = create_staff_user(username="bob", first_name="Bob", last_name="Jones")
        self.shared_terminal = create_shared_terminal(username="workshop-terminal")
        self.autocomplete_url = reverse("api-maintainer-autocomplete")

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.autocomplete_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_staff_permission(self):
        """Non-staff users should be denied access."""
        create_user(username="regular")
        self.client.login(username="regular", password="testpass123")
        response = self.client.get(self.autocomplete_url)
        self.assertEqual(response.status_code, 403)

    def test_returns_maintainers_list(self):
        """Should return a list of maintainers."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("maintainers", data)
        self.assertIsInstance(data["maintainers"], list)

    def test_excludes_shared_accounts(self):
        """Shared accounts should not appear in the autocomplete list."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url)

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]
        usernames = [m["username"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)
        self.assertIn("Bob Jones", display_names)
        self.assertNotIn("workshop-terminal", usernames)

    def test_filters_by_query(self):
        """Should filter results by query parameter."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url + "?q=alice")

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)
        self.assertNotIn("Bob Jones", display_names)

    def test_case_insensitive_filter(self):
        """Query filtering should be case-insensitive."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url + "?q=ALICE")

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)

    def test_returns_sorted_results(self):
        """Results should be sorted alphabetically by display name."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url)

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertEqual(display_names, sorted(display_names, key=str.lower))


@tag("api")
class ReceiveTranscodedMediaViewTests(TestDataMixin, TestCase):
    """Tests for the HTTP API endpoint that receives transcoded media from worker service."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test log entry")

        original_file = SimpleUploadedFile(
            "original.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_VIDEO,
            file=original_file,
            transcode_status=LogEntryMedia.STATUS_PROCESSING,
        )

        self.test_token = "test-secret-token-12345"  # noqa: S105
        settings.TRANSCODING_UPLOAD_TOKEN = self.test_token
        self.upload_url = reverse("api-transcoding-upload")

    def tearDown(self):
        settings.TRANSCODING_UPLOAD_TOKEN = None

    def test_requires_authorization_header(self):
        """Request without Authorization header should be rejected."""
        response = self.client.post(self.upload_url, {})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing or invalid Authorization header", response.json()["error"])

    def test_rejects_invalid_token(self):
        """Request with wrong token should be rejected."""
        response = self.client.post(self.upload_url, {}, HTTP_AUTHORIZATION="Bearer wrong-token")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid authentication token", response.json()["error"])

    def test_requires_log_entry_media_id(self):
        """Request without log_entry_media_id should be rejected."""
        response = self.client.post(
            self.upload_url, {}, HTTP_AUTHORIZATION=f"Bearer {self.test_token}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing log_entry_media_id", response.json()["error"])

    def test_requires_video_file(self):
        """Request without video_file should be rejected."""
        response = self.client.post(
            self.upload_url,
            {"log_entry_media_id": str(self.media.id)},
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing video_file", response.json()["error"])

    def test_validates_video_file_type(self):
        """Video file must have video/* content type."""
        wrong_file = SimpleUploadedFile("fake.txt", b"not a video", content_type="text/plain")
        response = self.client.post(
            self.upload_url,
            {"log_entry_media_id": str(self.media.id), "video_file": wrong_file},
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid video file type", response.json()["error"])

    def test_validates_poster_file_type_if_provided(self):
        """Poster file must have image/* content type if provided."""
        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        wrong_poster = SimpleUploadedFile("poster.txt", b"not an image", content_type="text/plain")

        response = self.client.post(
            self.upload_url,
            {
                "log_entry_media_id": str(self.media.id),
                "video_file": video_file,
                "poster_file": wrong_poster,
            },
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid poster file type", response.json()["error"])

    def test_rejects_nonexistent_media_id(self):
        """Request with non-existent media ID should be rejected."""
        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        response = self.client.post(
            self.upload_url,
            {"log_entry_media_id": "999999", "video_file": video_file},
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["error"])

    def test_successful_upload_with_video_and_poster(self):
        """Successful upload should save files and update status."""
        video_file = SimpleUploadedFile(
            "transcoded.mp4", b"transcoded video content", content_type="video/mp4"
        )
        poster_file = SimpleUploadedFile(
            "poster.jpg", b"poster image content", content_type="image/jpeg"
        )

        response = self.client.post(
            self.upload_url,
            {
                "log_entry_media_id": str(self.media.id),
                "video_file": video_file,
                "poster_file": poster_file,
            },
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertIn("successfully", result["message"].lower())

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertTrue(self.media.poster_file)
        self.assertFalse(self.media.file)

    def test_successful_upload_without_poster(self):
        """Upload can succeed with video only (poster optional)."""
        video_file = SimpleUploadedFile(
            "transcoded.mp4", b"transcoded video content", content_type="video/mp4"
        )

        response = self.client.post(
            self.upload_url,
            {"log_entry_media_id": str(self.media.id), "video_file": video_file},
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertFalse(self.media.poster_file)

    def test_server_not_configured_for_uploads(self):
        """If TRANSCODING_UPLOAD_TOKEN is not set, should return 500."""
        settings.TRANSCODING_UPLOAD_TOKEN = None

        response = self.client.post(self.upload_url, {}, HTTP_AUTHORIZATION="Bearer some-token")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Server not configured", response.json()["error"])


@tag("api")
class DeleteMediaTests(TestDataMixin, TestCase):
    """Ensure deleting media removes associated files (file and thumbnail)."""

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password="testpass123")
        self.log_entry = create_log_entry(machine=self.machine, text="Test log entry")
        # Minimal valid PNG (1x1 transparent)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        original = SimpleUploadedFile("photo.png", png_data, content_type="image/png")
        converted = resize_image_file(original)
        thumb = resize_image_file(converted)
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_PHOTO,
            file=converted,
            thumbnail_file=thumb,
        )
        self.delete_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_deletes_all_media_files(self):
        """Deleting media removes file, thumbnail, and DB record."""
        file_name = self.media.file.name
        thumb_name = self.media.thumbnail_file.name

        response = self.client.post(
            self.delete_url, {"action": "delete_media", "media_id": self.media.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LogEntryMedia.objects.filter(id=self.media.id).exists())
        storage = self.media.file.storage
        self.assertFalse(storage.exists(file_name))
        self.assertFalse(storage.exists(thumb_name))
