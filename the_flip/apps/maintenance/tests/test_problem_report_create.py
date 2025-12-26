"""Tests for problem report creation views."""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_maintainer_user,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("views")
class ProblemReportCreateViewTests(TestDataMixin, TestCase):
    """Tests for the public problem report submission view."""

    def setUp(self):
        super().setUp()
        self.url = reverse("public-problem-report-create", kwargs={"slug": self.machine.slug})

    def test_create_view_accessible_without_login(self):
        """Problem report form should be accessible to anonymous users."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_form_public.html")

    def test_create_view_shows_correct_machine_name(self):
        """Problem report form should show the machine's name."""
        response = self.client.get(self.url)
        self.assertContains(response, self.machine.name)

    def test_create_problem_report_success(self):
        """Successfully creating a problem report should save it with correct data."""
        data = {
            "problem_type": ProblemReport.ProblemType.STUCK_BALL,
            "description": "Ball is stuck behind the bumpers",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.url)  # Redirects back to itself

        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        self.assertEqual(report.machine, self.machine)
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.STUCK_BALL)
        self.assertEqual(report.description, "Ball is stuck behind the bumpers")
        self.assertEqual(report.status, ProblemReport.Status.OPEN)
        self.assertEqual(report.ip_address, "192.168.1.100")

    def test_create_problem_report_with_other_type(self):
        """Problem type can be explicitly set to 'other'."""
        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": "Something is wrong",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.OTHER)

    def test_create_problem_report_captures_user_agent(self):
        """Problem report should capture the User-Agent header."""
        data = {
            "problem_type": ProblemReport.ProblemType.NO_CREDITS,
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
        maintainer = create_maintainer_user()
        self.client.force_login(maintainer)
        data = {
            "problem_type": ProblemReport.ProblemType.STUCK_BALL,
            "description": "Ball locked up",
        }
        self.client.post(self.url, data, REMOTE_ADDR="203.0.113.42")

        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, maintainer)
        self.assertEqual(report.ip_address, "203.0.113.42")

    def test_rate_limiting_blocks_excessive_submissions(self):
        """Rate limiting should block submissions after exceeding the limit."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.ProblemType.OTHER,
                "description": f"Report {i + 1}",
            }
            response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
            self.assertEqual(response.status_code, 302)

        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": "This should be blocked",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP)

    def test_rate_limiting_allows_different_ips(self):
        """Rate limiting should be per IP address."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.ProblemType.OTHER,
                "description": f"Report from IP1 - {i + 1}",
            }
            self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": "Report from different IP",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.200")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)

    def test_rate_limiting_window_expires(self):
        """Rate limiting should reset after the time window expires."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.ProblemType.OTHER,
                "description": f"Report {i + 1}",
            }
            self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        old_time = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES + 1)
        ProblemReport.objects.all().update(created_at=old_time)

        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": "This should succeed after window expires",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)
