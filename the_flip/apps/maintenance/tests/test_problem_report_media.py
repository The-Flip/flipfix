"""Tests for problem report media upload, delete, and display."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TemporaryMediaMixin,
    TestDataMixin,
    create_problem_report,
    create_uploaded_image,
)
from the_flip.apps.maintenance.models import ProblemReport, ProblemReportMedia


@tag("views", "media")
class ProblemReportMediaCreateTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media upload on problem report create page (maintainer)."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse(
            "problem-report-create-machine", kwargs={"slug": self.machine.slug}
        )

    def test_create_with_media_upload(self):
        """Maintainer can upload media when creating a problem report."""
        self.client.force_login(self.maintainer_user)

        data = {
            "description": "Problem with media",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        # Maintainer form defaults to "Other" problem type
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.OTHER)
        self.assertEqual(report.media.count(), 1)
        media = report.media.first()
        self.assertEqual(media.media_type, ProblemReportMedia.MediaType.PHOTO)

    def test_create_without_media(self):
        """Problem report can be created without media."""
        self.client.force_login(self.maintainer_user)

        data = {
            "description": "No media attached",
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        # Maintainer form defaults to "Other" problem type
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.OTHER)
        self.assertEqual(report.media.count(), 0)

    def test_public_form_has_no_media_field(self):
        """Public problem report form should not have media upload field."""
        public_url = reverse("public-problem-report-create", kwargs={"slug": self.machine.slug})
        response = self.client.get(public_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="media_file"')


@tag("views", "ajax", "media")
class ProblemReportMediaUploadTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media upload on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_upload_media_requires_staff(self):
        """Non-staff users cannot upload media."""
        self.client.force_login(self.regular_user)

        data = {
            "action": "upload_media",
            "media_file": create_uploaded_image(),
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProblemReportMedia.objects.count(), 0)

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

        self.assertEqual(ProblemReportMedia.objects.count(), 1)
        media = ProblemReportMedia.objects.first()
        self.assertEqual(media.problem_report, self.report)
        self.assertEqual(media.media_type, ProblemReportMedia.MediaType.PHOTO)

    @patch("the_flip.apps.core.mixins.enqueue_transcode")
    def test_video_upload_enqueues_transcode_with_model_name(self, mock_enqueue):
        """Video upload should call enqueue_transcode with correct model_name.

        This test verifies that when a video is uploaded via AJAX to a problem report,
        the view correctly calls enqueue_transcode with model_name="ProblemReportMedia".
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
        media = ProblemReportMedia.objects.first()
        mock_enqueue.assert_called_once_with(media_id=media.id, model_name="ProblemReportMedia")


@tag("views", "ajax", "media")
class ProblemReportMediaDeleteTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media delete on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

        img_file = create_uploaded_image()
        self.media = ProblemReportMedia.objects.create(
            problem_report=self.report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", img_file.read(), content_type="image/jpeg"),
        )

    def test_delete_media_requires_staff(self):
        """Non-staff users cannot delete media."""
        self.client.force_login(self.regular_user)

        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProblemReportMedia.objects.count(), 1)

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
        self.assertEqual(ProblemReportMedia.objects.count(), 0)

    def test_delete_media_wrong_report(self):
        """Cannot delete media from another problem report."""
        other_report = create_problem_report(
            machine=self.machine,
            description="Other problem",
        )

        img_file = create_uploaded_image()
        other_media = ProblemReportMedia.objects.create(
            problem_report=other_report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("other.jpg", img_file.read(), content_type="image/jpeg"),
        )

        self.client.force_login(self.maintainer_user)

        # Try to delete other_media from this report's detail page
        data = {
            "action": "delete_media",
            "media_id": other_media.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 404)
        # other_media should still exist
        self.assertTrue(ProblemReportMedia.objects.filter(pk=other_media.pk).exists())


@tag("views", "media")
class ProblemReportDetailMediaDisplayTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media display on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

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
        ProblemReportMedia.objects.create(
            problem_report=self.report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("test.jpg", img_file.read(), content_type="image/jpeg"),
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "media-grid__item")
        self.assertNotContains(response, "No media.")
