"""Tests for maintenance app views and functionality."""

import shutil
import subprocess
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.maintenance.forms import LogEntryQuickForm
from the_flip.apps.maintenance.models import LogEntry, ProblemReport

User = get_user_model()


class FFmpegAvailabilityTest(TestCase):
    """Ensure ffmpeg/ffprobe are available for video processing."""

    def test_ffmpeg_available(self):
        if not shutil.which("ffmpeg"):
            self.fail("ffmpeg not found on PATH (video upload/transcode will fail)")
        result = subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertIn("ffmpeg version", (result.stdout or "").lower())

    def test_ffprobe_available(self):
        if not shutil.which("ffprobe"):
            self.fail("ffprobe not found on PATH (video upload/transcode will fail)")
        result = subprocess.run(
            ["ffprobe", "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertIn("ffprobe version", (result.stdout or "").lower())


class ProblemReportDetailViewTests(TestCase):
    """Tests for the problem report detail view."""

    def setUp(self):
        """Set up test data for problem report detail view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )

        # Create a problem report
        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball is stuck in the upper playfield",
            reported_by_name="John Doe",
            reported_by_contact="john@example.com",
            device_info="iPhone 12",
            ip_address="192.168.1.1",
        )

        # Create staff user (maintainer)
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        # Create regular user (non-staff)
        self.regular_user = User.objects.create_user(
            username="regularuser",
            password="testpass123",
            is_staff=False,
        )

        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_detail_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_detail_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_staff(self):
        """Staff users should be able to access the detail page."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_detail.html")

    def test_detail_view_displays_report_information(self):
        """Detail page should display all report information."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.machine.display_name)
        self.assertContains(response, "Stuck Ball")
        self.assertContains(response, "Ball is stuck in the upper playfield")
        self.assertContains(response, "John Doe")
        self.assertContains(response, "john@example.com")
        self.assertContains(response, "iPhone 12")
        self.assertContains(response, "192.168.1.1")
        self.assertContains(response, "Open")

    def test_detail_view_with_reported_by_user_hides_device_information(self):
        """If report was submitted by a logged-in user, only show the user."""
        submitter = User.objects.create_user(
            username="reportsubmitter",
            password="testpass123",
            first_name="Report",
            last_name="Submitter",
            is_staff=True,
        )
        self.report.reported_by_user = submitter
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Report Submitter")
        self.assertNotContains(response, "John Doe")
        self.assertNotContains(response, "john@example.com")
        self.assertNotContains(response, "iPhone 12")
        self.assertNotContains(response, "192.168.1.1")

    def test_detail_view_shows_close_button_for_open_report(self):
        """Detail page should show 'Close Problem Report' button for open reports."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Close Problem Report")
        self.assertNotContains(response, "Re-Open Problem Report")

    def test_detail_view_shows_reopen_button_for_closed_report(self):
        """Detail page should show 'Re-Open Problem Report' button for closed reports."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Re-Open Problem Report")
        self.assertNotContains(response, "Close Problem Report")

    def test_status_toggle_requires_staff(self):
        """Non-staff users should not be able to toggle status."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, 403)

        # Verify status was not changed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_from_open_to_closed(self):
        """Staff users should be able to close an open report."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        # Should redirect back to detail page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        # Verify status was toggled to closed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_CLOSED)

    def test_status_toggle_from_closed_to_open(self):
        """Staff users should be able to re-open a closed report."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        # Should redirect back to detail page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        # Verify status was toggled to open
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_shows_close_message(self):
        """Closing a report should show appropriate success message."""
        self.client.login(username="staffuser", password="testpass123")

        # Close the report
        response = self.client.post(self.detail_url, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report closed.")

    def test_status_toggle_shows_reopen_message(self):
        """Re-opening a report should show appropriate success message."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")

        # Re-open the report
        response = self.client.post(self.detail_url, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report re-opened.")


class ProblemReportListViewTests(TestCase):
    """Tests for the global problem report list view."""

    def setUp(self):
        """Set up test data for list view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )

        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_OTHER,
            description="Test problem",
        )

        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regularuser",
            password="testpass123",
            is_staff=False,
        )

        self.list_url = reverse("problem-report-list")

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list page."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_list_view_contains_link_to_detail(self):
        """List view should contain links to detail pages."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)


class MachineProblemReportListViewTests(TestCase):
    """Tests for the machine-specific problem report list view."""

    def setUp(self):
        """Set up test data for machine problem report list view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )

        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_OTHER,
            description="Test problem",
        )

        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        self.machine_list_url = reverse(
            "machine-problem-reports", kwargs={"slug": self.machine.slug}
        )

    def test_machine_list_view_contains_link_to_detail(self):
        """Machine-specific list view should contain links to detail pages."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.machine_list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)


class ProblemReportCreateViewTests(TestCase):
    """Tests for the public problem report submission view."""

    def setUp(self):
        """Set up test data for problem report create view tests."""
        # Create a machine model
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )

        self.url = reverse("problem-report-create", kwargs={"slug": self.machine.slug})

    def test_create_view_accessible_without_login(self):
        """Problem report form should be accessible to anonymous users."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_form.html")

    def test_create_view_shows_correct_machine_name(self):
        """Problem report form should show the machine's display name."""
        response = self.client.get(self.url)
        self.assertContains(response, self.machine.display_name)

    def test_create_problem_report_success(self):
        """Successfully creating a problem report should save it with correct data."""
        data = {
            "problem_type": ProblemReport.PROBLEM_STUCK_BALL,
            "description": "Ball is stuck behind the bumpers",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        # Should redirect to machine detail page
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.machine.get_absolute_url())

        # Report should be created
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        self.assertEqual(report.machine, self.machine)
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_STUCK_BALL)
        self.assertEqual(report.description, "Ball is stuck behind the bumpers")
        self.assertEqual(report.status, ProblemReport.STATUS_OPEN)
        self.assertEqual(report.ip_address, "192.168.1.100")

    def test_create_problem_report_with_other_type(self):
        """Problem type can be explicitly set to 'other'."""
        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "Something is wrong",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        # Should succeed
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_OTHER)

    def test_create_problem_report_captures_user_agent(self):
        """Problem report should capture the User-Agent header."""
        data = {
            "problem_type": ProblemReport.PROBLEM_NO_CREDITS,
            "description": "Credits not working",
        }
        self.client.post(
            self.url,
            data,
            REMOTE_ADDR="192.168.1.100",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        )

        report = ProblemReport.objects.first()
        self.assertIn("iPhone", report.device_info)
        self.assertIn("Mozilla", report.device_info)

    def test_create_problem_report_records_logged_in_user(self):
        """Submitting while authenticated should set reported_by_user."""
        maintainer = User.objects.create_user(
            username="maintainer",
            password="testpass123",
            is_staff=True,
        )
        self.client.login(username="maintainer", password="testpass123")
        data = {
            "problem_type": ProblemReport.PROBLEM_STUCK_BALL,
            "description": "Ball locked up",
        }
        self.client.post(self.url, data, REMOTE_ADDR="203.0.113.42")

        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, maintainer)
        self.assertEqual(report.ip_address, "203.0.113.42")

    def test_rate_limiting_blocks_excessive_submissions(self):
        """Rate limiting should block submissions after exceeding the limit."""
        # Submit reports up to the rate limit
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report {i+1}",
            }
            response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
            self.assertEqual(response.status_code, 302)

        # The next submission should be blocked
        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "This should be blocked",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        # Should still redirect (to machine detail with error message)
        self.assertEqual(response.status_code, 302)

        # Should NOT create a new report (still at the limit)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP)

    def test_rate_limiting_allows_different_ips(self):
        """Rate limiting should be per IP address."""
        # Submit reports from first IP up to the limit
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report from IP1 - {i+1}",
            }
            response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        # Submission from a different IP should succeed
        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "Report from different IP",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.200")
        self.assertEqual(response.status_code, 302)

        # Should create the new report
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)

    def test_rate_limiting_window_expires(self):
        """Rate limiting should reset after the time window expires."""
        # Submit reports up to the limit
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report {i+1}",
            }
            self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        # Manually update the created_at timestamp to be outside the rate limit window
        old_time = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES + 1)
        ProblemReport.objects.all().update(created_at=old_time)

        # New submission should now succeed
        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "This should succeed after window expires",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)

        # Should create a new report
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)


class ReceiveTranscodedMediaViewTests(TestCase):
    """Tests for the HTTP API endpoint that receives transcoded media from worker service."""

    def setUp(self):
        """Set up test data for API endpoint tests."""

        from django.core.files.uploadedfile import SimpleUploadedFile

        from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia

        # Create machine and log entry
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )
        self.log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test log entry",
        )

        # Create original media record with a fake video file
        original_file = SimpleUploadedFile(
            "original.mp4", b"fake video content", content_type="video/mp4"
        )
        self.media = LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            media_type=LogEntryMedia.TYPE_VIDEO,
            file=original_file,
            transcode_status=LogEntryMedia.STATUS_PROCESSING,
        )

        # Set up test token
        self.test_token = "test-secret-token-12345"  # noqa: S105
        settings.TRANSCODING_UPLOAD_TOKEN = self.test_token

        self.upload_url = reverse("api-transcoding-upload")

    def tearDown(self):
        """Clean up after tests."""
        # Reset settings
        settings.TRANSCODING_UPLOAD_TOKEN = None

    def test_requires_authorization_header(self):
        """Request without Authorization header should be rejected."""
        response = self.client.post(self.upload_url, {})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing or invalid Authorization header", response.json()["error"])

    def test_rejects_invalid_token(self):
        """Request with wrong token should be rejected."""
        response = self.client.post(
            self.upload_url,
            {},
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid authentication token", response.json()["error"])

    def test_requires_log_entry_media_id(self):
        """Request without log_entry_media_id should be rejected."""
        response = self.client.post(
            self.upload_url,
            {},
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
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
        from django.core.files.uploadedfile import SimpleUploadedFile

        wrong_file = SimpleUploadedFile("fake.txt", b"not a video", content_type="text/plain")
        response = self.client.post(
            self.upload_url,
            {
                "log_entry_media_id": str(self.media.id),
                "video_file": wrong_file,
            },
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid video file type", response.json()["error"])

    def test_validates_poster_file_type_if_provided(self):
        """Poster file must have image/* content type if provided."""
        from django.core.files.uploadedfile import SimpleUploadedFile

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
        from django.core.files.uploadedfile import SimpleUploadedFile

        video_file = SimpleUploadedFile("video.mp4", b"fake video", content_type="video/mp4")
        response = self.client.post(
            self.upload_url,
            {
                "log_entry_media_id": "999999",
                "video_file": video_file,
            },
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["error"])

    def test_successful_upload_with_video_and_poster(self):
        """Successful upload should save files and update status."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from the_flip.apps.maintenance.models import LogEntryMedia

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

        # Verify media record was updated
        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertTrue(self.media.poster_file)
        # Original file should be deleted
        self.assertFalse(self.media.file)

    def test_successful_upload_without_poster(self):
        """Upload can succeed with video only (poster optional)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from the_flip.apps.maintenance.models import LogEntryMedia

        video_file = SimpleUploadedFile(
            "transcoded.mp4", b"transcoded video content", content_type="video/mp4"
        )

        response = self.client.post(
            self.upload_url,
            {
                "log_entry_media_id": str(self.media.id),
                "video_file": video_file,
            },
            HTTP_AUTHORIZATION=f"Bearer {self.test_token}",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        # Verify media record was updated
        self.media.refresh_from_db()
        self.assertEqual(self.media.transcode_status, LogEntryMedia.STATUS_READY)
        self.assertTrue(self.media.transcoded_file)
        self.assertFalse(self.media.poster_file)  # No poster uploaded

    def test_server_not_configured_for_uploads(self):
        """If TRANSCODING_UPLOAD_TOKEN is not set, should return 500."""
        settings.TRANSCODING_UPLOAD_TOKEN = None

        response = self.client.post(
            self.upload_url,
            {},
            HTTP_AUTHORIZATION="Bearer some-token",
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Server not configured", response.json()["error"])


class LogEntryWorkDateTests(TestCase):
    """Tests for LogEntry work_date field."""

    def setUp(self):
        """Set up test data."""
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )

    def test_work_date_defaults_to_now(self):
        """LogEntry work_date should default to current time."""
        before = timezone.now()
        log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test entry",
        )
        after = timezone.now()

        self.assertIsNotNone(log_entry.work_date)
        self.assertGreaterEqual(log_entry.work_date, before)
        self.assertLessEqual(log_entry.work_date, after)

    def test_work_date_can_be_set_explicitly(self):
        """LogEntry work_date can be set to a specific datetime."""
        specific_date = timezone.now() - timedelta(days=5)
        log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Historical entry",
            work_date=specific_date,
        )

        self.assertEqual(log_entry.work_date, specific_date)

    def test_log_entries_ordered_by_work_date_descending(self):
        """LogEntry queryset should be ordered by work_date descending."""
        old_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Old entry",
            work_date=timezone.now() - timedelta(days=10),
        )
        new_entry = LogEntry.objects.create(
            machine=self.machine,
            text="New entry",
            work_date=timezone.now(),
        )

        entries = list(LogEntry.objects.all())
        self.assertEqual(entries[0], new_entry)
        self.assertEqual(entries[1], old_entry)


class LogEntryQuickFormWorkDateTests(TestCase):
    """Tests for LogEntryQuickForm work_date validation."""

    def test_form_valid_with_past_date(self):
        """Form should be valid with a past work_date."""
        past_date = timezone.now() - timedelta(days=5)
        form_data = {
            "work_date": past_date.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_valid_with_today(self):
        """Form should be valid with today's date."""
        today = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        form_data = {
            "work_date": today.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_invalid_with_future_date(self):
        """Form should be invalid with a future work_date."""
        future_date = timezone.now() + timedelta(days=5)
        form_data = {
            "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("work_date", form.errors)
        self.assertIn("future", form.errors["work_date"][0].lower())


class MachineLogCreateViewWorkDateTests(TestCase):
    """Tests for MachineLogCreateView work_date handling."""

    def setUp(self):
        """Set up test data."""
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_log_entry_with_work_date(self):
        """Creating a log entry should save the work_date."""
        self.client.login(username="staffuser", password="testpass123")

        work_date = timezone.now() - timedelta(days=3)
        response = self.client.post(
            self.create_url,
            {
                "work_date": work_date.strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Work performed three days ago",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        # Compare dates (ignoring seconds since form doesn't capture them)
        self.assertEqual(
            log_entry.work_date.strftime("%Y-%m-%d %H:%M"),
            work_date.strftime("%Y-%m-%d %H:%M"),
        )

    def test_create_log_entry_rejects_future_date(self):
        """Creating a log entry with future date should fail validation."""
        self.client.login(username="staffuser", password="testpass123")

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.create_url,
            {
                "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Future work",
            },
        )

        # Should re-render form with errors (200), not redirect
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LogEntry.objects.count(), 0)


class LogEntryDetailViewWorkDateTests(TestCase):
    """Tests for LogEntryDetailView work_date AJAX update."""

    def setUp(self):
        """Set up test data."""
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )
        self.log_entry = LogEntry.objects.create(
            machine=self.machine,
            text="Test entry",
        )
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_work_date_ajax(self):
        """AJAX update_work_date action should update the work_date."""
        self.client.login(username="staffuser", password="testpass123")

        new_date = timezone.now() - timedelta(days=7)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": new_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertEqual(
            self.log_entry.work_date.strftime("%Y-%m-%d %H:%M"),
            new_date.strftime("%Y-%m-%d %H:%M"),
        )

    def test_update_work_date_rejects_future(self):
        """AJAX update_work_date should reject future dates."""
        self.client.login(username="staffuser", password="testpass123")

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("future", result["error"].lower())

    def test_update_work_date_rejects_invalid_format(self):
        """AJAX update_work_date should reject invalid date formats."""
        self.client.login(username="staffuser", password="testpass123")

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": "not-a-valid-date",
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("Invalid date format", result["error"])

    def test_update_work_date_rejects_empty(self):
        """AJAX update_work_date should reject empty date."""
        self.client.login(username="staffuser", password="testpass123")

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])


class LogEntryCreatedByTests(TestCase):
    """Tests for LogEntry created_by field."""

    def setUp(self):
        """Set up test data."""
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            operational_status=MachineInstance.STATUS_GOOD,
        )
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_created_by_set_when_creating_log_entry(self):
        """Creating a log entry should set the created_by field."""
        self.client.login(username="staffuser", password="testpass123")

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Some Other Person",
                "text": "Work performed",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.created_by, self.staff_user)

    def test_created_by_can_differ_from_maintainer(self):
        """created_by (who entered data) can be different from maintainer (who did work)."""
        # Create another maintainer who did the work
        work_doer = User.objects.create_user(
            username="workdoer",
            first_name="Work",
            last_name="Doer",
            password="testpass123",
            is_staff=True,
        )

        self.client.login(username="staffuser", password="testpass123")

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Work Doer",  # Name of who did the work
                "text": "Work performed by someone else",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()

        # created_by is the logged-in user (who entered the data)
        self.assertEqual(log_entry.created_by, self.staff_user)

        # maintainers is who did the actual work
        self.assertIn(Maintainer.objects.get(user=work_doer), log_entry.maintainers.all())


class MaintainerAutocompleteViewTests(TestCase):
    """Tests for the maintainer autocomplete API endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create regular maintainers
        self.user1 = User.objects.create_user(
            username="alice",
            first_name="Alice",
            last_name="Smith",
            password="testpass123",
            is_staff=True,
        )
        self.user2 = User.objects.create_user(
            username="bob",
            first_name="Bob",
            last_name="Jones",
            password="testpass123",
            is_staff=True,
        )
        # Create a shared account
        self.shared_user = User.objects.create_user(
            username="workshop-terminal",
            password="testpass123",
            is_staff=True,
        )
        shared_maintainer = Maintainer.objects.get(user=self.shared_user)
        shared_maintainer.is_shared_account = True
        shared_maintainer.save()

        self.autocomplete_url = reverse("api-maintainer-autocomplete")

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.autocomplete_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_staff_permission(self):
        """Non-staff users should be denied access."""
        User.objects.create_user(username="regular", password="testpass123", is_staff=False)
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
        names = [m["name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", names)
        self.assertIn("Bob Jones", names)
        self.assertNotIn("workshop-terminal", names)

    def test_filters_by_query(self):
        """Should filter results by query parameter."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url + "?q=alice")

        data = response.json()
        names = [m["name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", names)
        self.assertNotIn("Bob Jones", names)

    def test_case_insensitive_filter(self):
        """Query filtering should be case-insensitive."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url + "?q=ALICE")

        data = response.json()
        names = [m["name"] for m in data["maintainers"]]

        self.assertIn("Alice Smith", names)

    def test_returns_sorted_results(self):
        """Results should be sorted alphabetically."""
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(self.autocomplete_url)

        data = response.json()
        names = [m["name"] for m in data["maintainers"]]

        self.assertEqual(names, sorted(names, key=str.lower))
