"""Tests for problem report creation views."""

from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.models import RecordReference
from flipfix.apps.core.test_utils import (
    DATETIME_INPUT_FORMAT,
    SharedAccountTestMixin,
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from flipfix.apps.maintenance.models import ProblemReport


@tag("views")
class ProblemReportCreateViewTests(TestDataMixin, TestCase):
    """Tests for the public problem report submission view."""

    def setUp(self):
        super().setUp()
        self.url = reverse("public-problem-report-create", kwargs={"code": self.machine.asset_id})

    def test_create_view_accessible_without_login(self):
        """Problem report form should be accessible to anonymous users."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_new_public.html")

    def test_create_view_shows_correct_machine_name(self):
        """Problem report form should show the machine's name."""
        response = self.client.get(self.url)
        self.assertContains(response, self.machine.name)

    def test_resolves_by_asset_id_case_insensitively(self):
        """The QR route resolves a machine by its asset ID, ignoring case."""
        url = reverse(
            "public-problem-report-create",
            kwargs={"code": self.machine.asset_id.lower()},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["machine"], self.machine)

    def test_resolves_by_legacy_slug(self):
        """Older QR codes encoding the machine slug still resolve (backward compat)."""
        url = reverse("public-problem-report-create", kwargs={"code": self.machine.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["machine"], self.machine)

    def test_legacy_slug_submission_creates_report(self):
        """A report submitted via a legacy slug URL is created and redirects."""
        url = reverse("public-problem-report-create", kwargs={"code": self.machine.slug})
        response = self.client.post(url, {"description": "Ball stuck"}, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        self.assertEqual(ProblemReport.objects.first().machine, self.machine)

    def test_unknown_code_returns_404(self):
        """A code matching neither an asset ID nor a slug returns 404."""
        url = reverse("public-problem-report-create", kwargs={"code": "no-such-machine"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_form_has_no_problem_type_field(self):
        """The problem-type radios were removed from the public form."""
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="problem_type"')
        self.assertNotIn("problem_type", response.context["form"].fields)

    def test_description_is_required(self):
        """An empty submission is rejected: describing the problem is required."""
        response = self.client.post(self.url, {"description": ""}, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "description", "This field is required.")
        self.assertEqual(ProblemReport.objects.count(), 0)

    def test_create_problem_report_success(self):
        """Successfully creating a problem report should save it with correct data."""
        data = {"description": "Ball is stuck behind the bumpers"}
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.url)  # Redirects back to itself

        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        self.assertEqual(report.machine, self.machine)
        # Public reports no longer collect a type; it falls back to the model default.
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.OTHER)
        self.assertEqual(report.description, "Ball is stuck behind the bumpers")
        self.assertEqual(report.status, ProblemReport.Status.OPEN)
        self.assertEqual(report.ip_address, "192.168.1.100")

    def test_visitor_report_gets_untriaged_priority(self):
        """Public submissions should always be set to UNTRIAGED priority."""
        self.client.post(self.url, {"description": "Ball stuck"}, REMOTE_ADDR="192.168.1.100")

        report = ProblemReport.objects.first()
        self.assertEqual(report.priority, ProblemReport.Priority.UNTRIAGED)

    def test_create_problem_report_captures_user_agent(self):
        """Problem report should capture the User-Agent header."""
        data = {"description": "Credits not working"}
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
        self.client.force_login(self.maintainer_user)
        data = {
            "problem_type": ProblemReport.ProblemType.STUCK_BALL,
            "description": "Ball locked up",
        }
        self.client.post(self.url, data, REMOTE_ADDR="203.0.113.42")

        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, self.maintainer_user)
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

    def test_public_form_does_not_convert_links(self):
        """Public form stores description verbatim without link conversion."""
        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": f"See [[machine:{self.machine.slug}]]",
        }
        self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        report = ProblemReport.objects.first()
        # Public form should store text as-is, not convert to storage format
        self.assertEqual(report.description, f"See [[machine:{self.machine.slug}]]")

    def test_public_form_does_not_reject_broken_links(self):
        """Public form accepts text with unresolvable link syntax."""
        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": "See [[machine:nonexistent]]",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        self.assertEqual(report.description, "See [[machine:nonexistent]]")

    def test_public_form_does_not_create_references(self):
        """Public form does not create RecordReference rows."""
        data = {
            "problem_type": ProblemReport.ProblemType.OTHER,
            "description": f"See [[machine:{self.machine.slug}]]",
        }
        self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        source_ct = ContentType.objects.get_for_model(ProblemReport)
        report = ProblemReport.objects.first()
        self.assertFalse(
            RecordReference.objects.filter(
                source_type=source_ct,
                source_id=report.pk,
            ).exists()
        )


@tag("views")
class MaintainerProblemReportCreateViewTests(TestDataMixin, TestCase):
    """Tests for the maintainer problem report creation view."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.maintainer_user)
        self.url = reverse("problem-report-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_with_empty_occurred_at_defaults_to_now(self):
        """When occurred_at is submitted empty, it should default to now.

        This tests a bug where HTML forms submit empty strings for empty inputs,
        which Django interprets as 'field present but empty' rather than 'field
        absent'. Without explicit handling, this would set occurred_at to None
        and fail validation on the non-nullable model field.
        """
        data = {
            "description": "Machine is broken",
            "priority": ProblemReport.Priority.MINOR,
            "occurred_at": "",  # Empty string, as submitted by HTML form
        }
        response = self.client.post(self.url, data)

        # Should succeed, not error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)

        report = ProblemReport.objects.first()
        # occurred_at should be set to approximately now, not None
        self.assertIsNotNone(report.occurred_at)
        # Should be within last minute
        time_diff = timezone.now() - report.occurred_at
        self.assertLess(time_diff.total_seconds(), 60)

    def test_maintainer_report_defaults_to_minor_priority(self):
        """Priority defaults to MINOR — the select renders it pre-selected."""
        response = self.client.get(self.url)
        form = response.context["form"]
        self.assertEqual(
            form.fields["priority"].initial,
            ProblemReport.Priority.MINOR,
        )

    def test_maintainer_can_set_custom_priority(self):
        """Maintainer can explicitly set priority on creation."""
        data = {
            "description": "Machine totally broken",
            "priority": ProblemReport.Priority.UNPLAYABLE,
            "occurred_at": "",
        }
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.priority, ProblemReport.Priority.UNPLAYABLE)

    def test_creating_unplayable_report_marks_machine_broken(self):
        """A maintainer filing an Unplayable report breaks the machine."""
        self.assertEqual(self.machine.operational_status, MachineInstance.OperationalStatus.GOOD)
        response = self.client.post(
            self.url,
            {
                "description": "Board is fried",
                "priority": ProblemReport.Priority.UNPLAYABLE,
                "occurred_at": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, MachineInstance.OperationalStatus.BROKEN)

    def test_create_rejects_future_date(self):
        """View rejects problem reports with future occurred_at dates."""
        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                "occurred_at": future_date.strftime(DATETIME_INPUT_FORMAT),
            },
        )

        # Should return form with error, not redirect
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "future")
        self.assertEqual(ProblemReport.objects.count(), 0)


@tag("views")
class ProblemReportSharedAccountTests(
    SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for problem report creation from shared/terminal accounts."""

    def setUp(self):
        super().setUp()
        self.url = reverse("problem-report-create-machine", kwargs={"slug": self.machine.slug})

    def test_shared_account_with_valid_username_uses_user_fk(self):
        """Shared account selecting from dropdown saves to reported_by_user."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                "reporter_name": str(self.identifying_maintainer),
                "reporter_name_username": self.identifying_user.username,
            },
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, self.identifying_user)
        self.assertEqual(report.reported_by_name, "")

    def test_shared_account_with_free_text_uses_text_field(self):
        """Shared account typing free text saves to reported_by_name field."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                "reporter_name": "Jane Visitor",
                "reporter_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertIsNone(report.reported_by_user)
        self.assertEqual(report.reported_by_name, "Jane Visitor")

    def test_shared_account_with_empty_name_shows_error(self):
        """Shared account with empty name shows form error."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                "reporter_name": "",
                "reporter_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertContains(response, "Please enter your name")
        self.assertEqual(ProblemReport.objects.count(), 0)

    def test_regular_account_with_no_reporter_uses_current_user(self):
        """Regular account with no reporter selection defaults to current user."""
        self.client.force_login(self.identifying_user)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                # No reporter_name or reporter_name_username
            },
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, self.identifying_user)

    def test_regular_account_with_freetext_name_saves_freetext(self):
        """Regular account typing unrecognized name should save as freetext.

        When a non-shared account types a name that doesn't match any user
        (e.g., "Jane Visitor"), it should be saved as freetext rather than
        silently falling back to the current user.
        """
        self.client.force_login(self.identifying_user)
        response = self.client.post(
            self.url,
            {
                "description": "Machine is broken",
                "priority": ProblemReport.Priority.MINOR,
                "reporter_name": "Jane Visitor",
                "reporter_name_username": "",  # No matching user
            },
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertIsNone(report.reported_by_user)
        self.assertEqual(report.reported_by_name, "Jane Visitor")
