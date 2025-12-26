"""Tests for maintenance app API endpoints."""

import secrets

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    MINIMAL_PNG,
    SuppressRequestLogsMixin,
    TemporaryMediaMixin,
    TestDataMixin,
    create_log_entry,
    create_maintainer_user,
    create_shared_terminal,
    create_user,
)
from the_flip.apps.maintenance.models import LogEntryMedia
from the_flip.apps.maintenance.utils import resize_image_file


@tag("views")
class MaintainerAutocompleteViewTests(SuppressRequestLogsMixin, TestCase):
    """Tests for the maintainer autocomplete API endpoint."""

    def setUp(self):
        self.user1 = create_maintainer_user(username="alice", first_name="Alice", last_name="Smith")
        self.user2 = create_maintainer_user(username="bob", first_name="Bob", last_name="Jones")
        self.shared_terminal = create_shared_terminal(username="workshop-terminal")
        self.autocomplete_url = reverse("api-maintainer-autocomplete")

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.autocomplete_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_staff_permission(self):
        """Non-staff users should be denied access."""
        regular = create_user()
        self.client.force_login(regular)
        response = self.client.get(self.autocomplete_url)
        self.assertEqual(response.status_code, 403)

    def test_returns_maintainers_list(self):
        """Should return a list of maintainers."""
        self.client.force_login(self.user1)
        response = self.client.get(self.autocomplete_url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("maintainers", data)
        self.assertIsInstance(data["maintainers"], list)

    def test_excludes_shared_accounts(self):
        """Shared accounts should not appear in the autocomplete list."""
        self.client.force_login(self.user1)
        response = self.client.get(self.autocomplete_url)

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]
        usernames = [m["username"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)
        self.assertIn("Bob Jones", display_names)
        self.assertNotIn("workshop-terminal", usernames)

    def test_filters_by_query(self):
        """Should filter results by query parameter."""
        self.client.force_login(self.user1)
        response = self.client.get(self.autocomplete_url + "?q=alice")

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)
        self.assertNotIn("Bob Jones", display_names)

    def test_case_insensitive_filter(self):
        """Query filtering should be case-insensitive."""
        self.client.force_login(self.user1)
        response = self.client.get(self.autocomplete_url + "?q=ALICE")

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", display_names)

    def test_returns_sorted_results(self):
        """Results should be sorted alphabetically by display name."""
        self.client.force_login(self.user1)
        response = self.client.get(self.autocomplete_url)

        data = response.json()
        display_names = [m["display_name"] for m in data["maintainers"]]

        self.assertEqual(display_names, sorted(display_names, key=str.lower))


@tag("views")
class ReceiveTranscodedMediaViewTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for the HTTP API endpoint that receives transcoded media from worker service."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test log entry")

        original_file = SimpleUploadedFile(
            "original.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.MediaType.VIDEO,
            file=original_file,
            transcode_status=LogEntryMedia.TranscodeStatus.PROCESSING,
        )

        # Generate token dynamically to avoid triggering secret scanners
        self.test_token = secrets.token_hex(16)

    def _build_upload_url(self, model_name: str = "LogEntryMedia", media_id: int | None = None):
        """Build upload URL with path parameters."""
        return reverse(
            "api-transcoding-upload",
            kwargs={"model_name": model_name, "media_id": media_id or self.media.id},
        )

    def _auth_headers(self, token: str | None = None) -> dict[str, str]:
        bearer = token or self.test_token
        return {"HTTP_AUTHORIZATION": f"Bearer {bearer}"}

    def test_requires_authorization_header(self):
        """Request without Authorization header should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(self._build_upload_url(), {})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing or invalid Authorization header", response.json()["error"])

    def test_rejects_invalid_token(self):
        """Request with wrong token should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(), {}, **self._auth_headers("wrong-token")
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid authentication token", response.json()["error"])

    def test_requires_video_file(self):
        """Request without video_file should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(self._build_upload_url(), {}, **self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing video_file", response.json()["error"])

    def test_validates_video_file_type(self):
        """Video file must have video/* content type."""
        wrong_file = SimpleUploadedFile("fake.txt", b"not a video", content_type="text/plain")
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(), {"video_file": wrong_file}, **self._auth_headers()
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid video file type", response.json()["error"])

    def test_validates_poster_file_type_if_provided(self):
        """Poster file must have image/* content type if provided."""
        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        wrong_poster = SimpleUploadedFile("poster.txt", b"not an image", content_type="text/plain")

        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(),
                {"video_file": video_file, "poster_file": wrong_poster},
                **self._auth_headers(),
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid poster file type", response.json()["error"])

    def test_rejects_nonexistent_media_id(self):
        """Request with non-existent media ID should be rejected."""
        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(media_id=999999),
                {"video_file": video_file},
                **self._auth_headers(),
            )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["error"])

    def test_rejects_invalid_model_name(self):
        """Request with invalid model_name should be rejected."""
        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(model_name="InvalidModel"),
                {"video_file": video_file},
                **self._auth_headers(),
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown media model", response.json()["error"])

    def test_successful_upload_with_video_and_poster(self):
        """Successful upload should save files and update status."""
        video_file = SimpleUploadedFile(
            "transcoded.mp4", b"transcoded video content", content_type="video/mp4"
        )
        poster_file = SimpleUploadedFile(
            "poster.jpg", b"poster image content", content_type="image/jpeg"
        )

        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(),
                {"video_file": video_file, "poster_file": poster_file},
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertIn("successfully", result["message"].lower())

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.TranscodeStatus.READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertTrue(self.media.poster_file)
        self.assertFalse(self.media.file)

    def test_successful_upload_without_poster(self):
        """Upload can succeed with video only (poster optional)."""
        video_file = SimpleUploadedFile(
            "transcoded.mp4", b"transcoded video content", content_type="video/mp4"
        )

        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.post(
                self._build_upload_url(), {"video_file": video_file}, **self._auth_headers()
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.TranscodeStatus.READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertFalse(self.media.poster_file)

    def test_server_not_configured_for_uploads(self):
        """If TRANSCODING_UPLOAD_TOKEN is not set, should return 500."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=None):
            response = self.client.post(
                self._build_upload_url(), {}, **self._auth_headers("some-token")
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Server not configured", response.json()["error"])


@tag("views")
class ServeSourceMediaViewTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for the HTTP API endpoint that serves source video files to worker service."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test log entry")

        original_file = SimpleUploadedFile(
            "original.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.MediaType.VIDEO,
            file=original_file,
            transcode_status=LogEntryMedia.TranscodeStatus.PENDING,
        )

        # Generate token dynamically to avoid triggering secret scanners
        self.test_token = secrets.token_hex(16)

    def _build_download_url(self, model_name: str = "LogEntryMedia", media_id: int | None = None):
        """Build download URL with path parameters."""
        return reverse(
            "api-transcoding-download",
            kwargs={"model_name": model_name, "media_id": media_id or self.media.id},
        )

    def _auth_headers(self, token: str | None = None) -> dict[str, str]:
        bearer = token or self.test_token
        return {"HTTP_AUTHORIZATION": f"Bearer {bearer}"}

    def test_requires_authorization_header(self):
        """Request without Authorization header should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(self._build_download_url())
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing or invalid Authorization header", response.json()["error"])

    def test_rejects_invalid_token(self):
        """Request with wrong token should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(
                self._build_download_url(), **self._auth_headers("wrong-token")
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid authentication token", response.json()["error"])

    def test_rejects_nonexistent_media_id(self):
        """Request with non-existent media ID should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(
                self._build_download_url(media_id=999999), **self._auth_headers()
            )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["error"])

    def test_rejects_invalid_model_name(self):
        """Request with invalid model_name should be rejected."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(
                self._build_download_url(model_name="InvalidModel"), **self._auth_headers()
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown media model", response.json()["error"])

    def test_successful_download(self):
        """Successful download should stream the file."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(self._build_download_url(), **self._auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "video/mp4")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"fake video content")

    def test_rejects_media_without_file(self):
        """Request for media without a source file should be rejected."""
        self.media.file.delete()
        self.media.save()

        with override_settings(TRANSCODING_UPLOAD_TOKEN=self.test_token):
            response = self.client.get(self._build_download_url(), **self._auth_headers())
        self.assertEqual(response.status_code, 404)
        self.assertIn("no source file", response.json()["error"])

    def test_server_not_configured_for_downloads(self):
        """If TRANSCODING_UPLOAD_TOKEN is not set, should return 500."""
        with override_settings(TRANSCODING_UPLOAD_TOKEN=None):
            response = self.client.get(
                self._build_download_url(), **self._auth_headers("some-token")
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Server not configured", response.json()["error"])


@tag("views")
class DeleteMediaTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Ensure deleting media removes associated files (file and thumbnail)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.maintainer_user)
        self.log_entry = create_log_entry(machine=self.machine, text="Test log entry")
        original = SimpleUploadedFile("photo.png", MINIMAL_PNG, content_type="image/png")
        converted = resize_image_file(original)
        thumb = resize_image_file(converted)
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.MediaType.PHOTO,
            file=converted,
            thumbnail_file=thumb,
        )
        self.delete_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_deletes_all_photo_files(self):
        """Deleting photo media removes everything associated with the photo: the photo file, thumbnail, and DB record."""
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

    def test_deletes_all_video_files(self):
        """Deleting video media removes everything associated with the video: the original, transcoded, poster, and DB record."""
        # Create video with all associated files
        original = SimpleUploadedFile("video.mp4", b"original", content_type="video/mp4")
        transcoded = SimpleUploadedFile("transcoded.mp4", b"transcoded", content_type="video/mp4")
        poster = SimpleUploadedFile("poster.jpg", b"poster", content_type="image/jpeg")

        video_media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.MediaType.VIDEO,
            file=original,
            transcoded_file=transcoded,
            poster_file=poster,
            transcode_status=LogEntryMedia.TranscodeStatus.READY,
        )

        original_name = video_media.file.name
        transcoded_name = video_media.transcoded_file.name
        poster_name = video_media.poster_file.name
        storage = video_media.file.storage

        response = self.client.post(
            self.delete_url, {"action": "delete_media", "media_id": video_media.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LogEntryMedia.objects.filter(id=video_media.id).exists())
        self.assertFalse(storage.exists(original_name))
        self.assertFalse(storage.exists(transcoded_name))
        self.assertFalse(storage.exists(poster_name))
