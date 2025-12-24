"""Tests for part request update media upload, delete, and display."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TemporaryMediaMixin,
    TestDataMixin,
    create_part_request,
    create_part_request_update,
    create_uploaded_image,
)
from the_flip.apps.parts.models import PartRequestUpdate, PartRequestUpdateMedia


@tag("views", "media")
class PartRequestUpdateMediaCreateTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media upload on part request update create page."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.create_url = reverse("part-request-update-create", kwargs={"pk": self.part_request.pk})

    def test_create_update_with_media(self):
        """Maintainer can upload media when creating an update."""
        self.client.force_login(self.maintainer_user)

        data = {
            "text": "Update with photo",
            "new_status": "",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequestUpdate.objects.count(), 1)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.media.count(), 1)
        media = update.media.first()
        self.assertEqual(media.media_type, PartRequestUpdateMedia.MediaType.PHOTO)
        self.assertEqual(media.transcode_status, "")

    def test_create_update_without_media(self):
        """Update can be created without media."""
        self.client.force_login(self.maintainer_user)

        data = {
            "text": "Update without media",
            "new_status": "",
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequestUpdate.objects.count(), 1)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.media.count(), 0)

    @patch("the_flip.apps.parts.views.enqueue_transcode")
    def test_form_video_upload_enqueues_transcode(self, mock_enqueue):
        """Video uploaded via form submission triggers transcoding."""
        self.client.force_login(self.maintainer_user)

        video_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.create_url,
                {
                    "text": "Update with video",
                    "new_status": "",
                    "media_file": video_file,
                },
            )

        self.assertEqual(response.status_code, 302)

        media = PartRequestUpdateMedia.objects.first()
        self.assertIsNotNone(media)
        self.assertEqual(media.media_type, PartRequestUpdateMedia.MediaType.VIDEO)
        self.assertEqual(media.transcode_status, PartRequestUpdateMedia.TranscodeStatus.PENDING)
        mock_enqueue.assert_called_once_with(media_id=media.id, model_name="PartRequestUpdateMedia")


@tag("views", "ajax", "media")
class PartRequestUpdateMediaUploadTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media upload on part request update detail page."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.update = create_part_request_update(
            part_request=self.part_request,
            text="Test update",
            posted_by=self.maintainer,
        )
        self.detail_url = reverse("part-request-update-detail", kwargs={"pk": self.update.pk})

    def test_upload_media_requires_auth(self):
        """Unauthenticated users are redirected to login."""
        data = {
            "action": "upload_media",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequestUpdateMedia.objects.count(), 0)

    def test_upload_media_requires_staff(self):
        """Non-staff users cannot upload media."""
        self.client.force_login(self.regular_user)

        data = {
            "action": "upload_media",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PartRequestUpdateMedia.objects.count(), 0)

    def test_upload_media_missing_file(self):
        """Missing media_file returns 400."""
        self.client.force_login(self.maintainer_user)

        data = {
            "action": "upload_media",
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data["success"])

    def test_upload_media_success(self):
        """Staff can upload media via AJAX."""
        self.client.force_login(self.maintainer_user)

        data = {
            "action": "upload_media",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertIn("media_id", json_data)
        self.assertEqual(json_data["media_type"], "photo")

        self.assertEqual(PartRequestUpdateMedia.objects.count(), 1)
        media = PartRequestUpdateMedia.objects.first()
        self.assertEqual(media.update, self.update)
        self.assertEqual(media.media_type, PartRequestUpdateMedia.MediaType.PHOTO)

    @patch("the_flip.apps.core.mixins.enqueue_transcode")
    def test_video_upload_enqueues_transcode_with_model_name(self, mock_enqueue):
        """Video upload should call enqueue_transcode with correct model_name.

        This test verifies that when a video is uploaded via AJAX to a part request update,
        the view correctly calls enqueue_transcode with model_name="PartRequestUpdateMedia".
        """
        self.client.force_login(self.maintainer_user)

        video_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.detail_url,
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
        media = PartRequestUpdateMedia.objects.first()
        self.assertEqual(media.transcode_status, PartRequestUpdateMedia.TranscodeStatus.PENDING)
        mock_enqueue.assert_called_once_with(media_id=media.id, model_name="PartRequestUpdateMedia")

    @patch("the_flip.apps.core.mixins.enqueue_transcode")
    def test_photo_upload_does_not_enqueue_transcode(self, mock_enqueue):
        """AJAX photo upload should NOT trigger video transcoding."""
        self.client.force_login(self.maintainer_user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.detail_url,
                {
                    "action": "upload_media",
                    "media_file": create_uploaded_image(),
                },
            )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["media_type"], "photo")

        # Verify enqueue_transcode was NOT called for photos
        mock_enqueue.assert_not_called()


@tag("views", "ajax", "media")
class PartRequestUpdateMediaDeleteTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media delete on part request update detail page."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.update = create_part_request_update(
            part_request=self.part_request,
            text="Test update",
            posted_by=self.maintainer,
        )
        self.detail_url = reverse("part-request-update-detail", kwargs={"pk": self.update.pk})

        img_file = create_uploaded_image()
        self.media = PartRequestUpdateMedia.objects.create(
            update=self.update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", img_file.read(), content_type="image/jpeg"),
        )

    def test_delete_media_requires_auth(self):
        """Unauthenticated users are redirected to login."""
        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequestUpdateMedia.objects.count(), 1)

    def test_delete_media_requires_staff(self):
        """Non-staff users cannot delete media."""
        self.client.force_login(self.regular_user)

        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PartRequestUpdateMedia.objects.count(), 1)

    def test_delete_media_missing_id(self):
        """Missing media_id returns 400."""
        self.client.force_login(self.maintainer_user)

        data = {
            "action": "delete_media",
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data["success"])

    def test_delete_media_success(self):
        """Staff can delete media via AJAX."""
        self.client.force_login(self.maintainer_user)

        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(PartRequestUpdateMedia.objects.count(), 0)

    def test_delete_media_wrong_update(self):
        """Cannot delete media from another update."""
        other_update = create_part_request_update(
            part_request=self.part_request,
            text="Other update",
            posted_by=self.maintainer,
        )

        img_file = create_uploaded_image()
        other_media = PartRequestUpdateMedia.objects.create(
            update=other_update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("other.jpg", img_file.read(), content_type="image/jpeg"),
        )

        self.client.force_login(self.maintainer_user)

        # Try to delete other_media from this update's detail page
        data = {
            "action": "delete_media",
            "media_id": other_media.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 404)
        # other_media should still exist
        self.assertTrue(PartRequestUpdateMedia.objects.filter(pk=other_media.pk).exists())


@tag("views", "media")
class PartRequestUpdateDetailMediaDisplayTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media display on part request update detail page."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.update = create_part_request_update(
            part_request=self.part_request,
            text="Test update",
            posted_by=self.maintainer,
        )
        self.detail_url = reverse("part-request-update-detail", kwargs={"pk": self.update.pk})

    def test_detail_shows_media_section(self):
        """Detail page should show Media section."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Media")
        self.assertContains(response, "Upload")

    def test_detail_shows_no_media_message(self):
        """Detail page should show 'No media' when there are no uploads."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "No media.")

    def test_detail_shows_uploaded_media(self):
        """Detail page should display uploaded media."""
        img_file = create_uploaded_image()
        PartRequestUpdateMedia.objects.create(
            update=self.update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", img_file.read(), content_type="image/jpeg"),
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "media-grid__item")
        self.assertNotContains(response, "No media.")
