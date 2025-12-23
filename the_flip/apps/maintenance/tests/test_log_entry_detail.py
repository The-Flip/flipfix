"""Tests for log entry detail view and AJAX updates."""

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    DATETIME_DISPLAY_FORMAT,
    DATETIME_INPUT_FORMAT,
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_problem_report,
)


@tag("views", "ajax")
class LogEntryDetailViewWorkDateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LogEntryDetailView AJAX work_date updates."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test entry")
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_work_date_ajax(self):
        """AJAX endpoint updates work_date successfully."""
        self.client.force_login(self.staff_user)

        new_date = timezone.now() - timedelta(days=7)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": new_date.strftime(DATETIME_INPUT_FORMAT),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertEqual(
            self.log_entry.work_date.strftime(DATETIME_DISPLAY_FORMAT),
            new_date.strftime(DATETIME_DISPLAY_FORMAT),
        )

    def test_update_work_date_rejects_future(self):
        """AJAX endpoint rejects future dates."""
        self.client.force_login(self.staff_user)

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": future_date.strftime(DATETIME_INPUT_FORMAT),
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("future", result["error"].lower())

    def test_update_work_date_rejects_invalid_format(self):
        """AJAX endpoint rejects invalid date formats."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_work_date", "work_date": "not-a-valid-date"},
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("Invalid date format", result["error"])

    def test_update_work_date_rejects_empty(self):
        """AJAX endpoint rejects empty date values."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url, {"action": "update_work_date", "work_date": ""}
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])


@tag("views", "ajax")
class LogEntryDetailViewTextUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LogEntryDetailView AJAX text updates."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Original text")
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_text_success(self):
        """AJAX endpoint updates text successfully."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.text, "Updated description")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty text."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.text, "")

    def test_update_text_requires_auth(self):
        """AJAX endpoint requires authentication."""
        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_text_requires_maintainer(self):
        """AJAX endpoint requires maintainer access."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 403)


@tag("views")
class LogEntryProblemReportUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for updating the problem report of a log entry via AJAX."""

    def setUp(self):
        super().setUp()
        self.other_machine = create_machine(slug="other-machine")
        self.problem_report = create_problem_report(
            machine=self.machine,
            description="Original problem",
        )
        self.other_problem_report = create_problem_report(
            machine=self.other_machine,
            description="Other problem",
        )
        self.log_entry = create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Linked log entry",
        )
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_problem_report_success(self):
        """Successfully update log entry's problem report."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.problem_report, self.other_problem_report)

    def test_update_problem_report_changes_machine(self):
        """Updating problem report also changes the machine to match."""
        self.client.force_login(self.staff_user)

        self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.machine, self.other_machine)

    def test_unlink_from_problem_report(self):
        """Setting problem_report_id to 'none' unlinks the log entry."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": "none",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertIsNone(self.log_entry.problem_report)
        # Machine should remain the same
        self.assertEqual(self.log_entry.machine, self.machine)

    def test_link_orphan_to_problem_report(self):
        """An orphan log entry can be linked to a problem report."""
        orphan_entry = create_log_entry(
            machine=self.machine,
            text="Orphan log entry",
        )
        detail_url = reverse("log-detail", kwargs={"pk": orphan_entry.pk})

        self.client.force_login(self.staff_user)
        response = self.client.post(
            detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        orphan_entry.refresh_from_db()
        self.assertEqual(orphan_entry.problem_report, self.other_problem_report)
        self.assertEqual(orphan_entry.machine, self.other_machine)

    def test_update_problem_report_noop_when_same(self):
        """Selecting the same problem report returns noop status."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "noop")

    def test_update_problem_report_invalid_id(self):
        """Invalid problem report ID returns 404 error."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": "99999",
            },
        )

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertFalse(result["success"])

    def test_update_problem_report_requires_maintainer_permission(self):
        """Regular users (non-maintainers) cannot update problem report."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 403)


@tag("views")
class LogEntryMachineUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for updating the machine of an orphan log entry via AJAX."""

    def setUp(self):
        super().setUp()
        self.other_machine = create_machine(slug="other-machine")
        self.orphan_entry = create_log_entry(
            machine=self.machine,
            text="Orphan log entry",
        )
        self.detail_url = reverse("log-detail", kwargs={"pk": self.orphan_entry.pk})

    def test_update_machine_success(self):
        """Successfully update orphan log entry's machine."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.orphan_entry.refresh_from_db()
        self.assertEqual(self.orphan_entry.machine, self.other_machine)

    def test_update_machine_noop_when_same(self):
        """Selecting the same machine returns noop status."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.machine.slug,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "noop")

    def test_update_machine_invalid_slug(self):
        """Invalid machine slug returns 404 error."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": "nonexistent-machine",
            },
        )

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertFalse(result["success"])

    def test_update_machine_rejected_for_linked_entry(self):
        """Updating machine directly on a linked log entry returns error."""
        linked_entry = create_log_entry(
            machine=self.machine,
            problem_report=create_problem_report(machine=self.machine),
            text="Linked log entry",
        )
        detail_url = reverse("log-detail", kwargs={"pk": linked_entry.pk})

        self.client.force_login(self.staff_user)
        response = self.client.post(
            detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("problem report", result["error"].lower())

    def test_update_machine_requires_maintainer_permission(self):
        """Regular users (non-maintainers) cannot update machine."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 403)
