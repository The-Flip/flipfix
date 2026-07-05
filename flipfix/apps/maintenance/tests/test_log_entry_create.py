"""Tests for log entry creation views."""

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.test_utils import (
    DATETIME_DISPLAY_FORMAT,
    DATETIME_INPUT_FORMAT,
    SharedAccountTestMixin,
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_maintainer_user,
    create_problem_report,
)
from flipfix.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class MachineLogCreateViewOccurredAtTests(TestDataMixin, TestCase):
    """Tests for MachineLogCreateView occurred_at handling."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_log_entry_with_occurred_at(self):
        """Creating a log entry saves the specified occurred_at."""
        self.client.force_login(self.maintainer_user)

        occurred_at = timezone.now() - timedelta(days=3)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": occurred_at.strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Work performed three days ago",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(
            log_entry.occurred_at.strftime(DATETIME_DISPLAY_FORMAT),
            occurred_at.strftime(DATETIME_DISPLAY_FORMAT),
        )

    def test_create_log_entry_rejects_future_date(self):
        """View rejects log entries with future occurred_at dates."""
        self.client.force_login(self.maintainer_user)

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": future_date.strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Future work",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_create_with_shared_account_username_only_defaults_to_current_user(self):
        """Regular user submitting with only shared account username defaults to current user.

        Shared accounts are filtered out of maintainer selections. If a regular user
        somehow submits with only a shared account username, it's treated as "no
        maintainer provided" and defaults to the current user.
        """
        from flipfix.apps.core.test_utils import create_shared_terminal

        shared = create_shared_terminal(username="terminal1")
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_usernames": shared.user.username,  # Shared account, filtered out
                # No maintainer_freetext
                "text": "Work performed",
            },
        )

        # Should succeed with current user as maintainer (shared account filtered out)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 1)
        self.assertIn(
            Maintainer.objects.get(user=self.maintainer_user),
            log_entry.maintainers.all(),
        )


@tag("views")
class LogEntryCreatedByTests(TestDataMixin, TestCase):
    """Tests for LogEntry created_by field via view."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_created_by_set_when_creating_log_entry(self):
        """Creating a log entry should set the created_by field."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Some Other Person",
                "text": "Work performed",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.created_by, self.maintainer_user)

    def test_created_by_can_differ_from_maintainer(self):
        """created_by (who entered data) can differ from maintainers (who did work)."""
        work_doer = create_maintainer_user(username="workdoer", first_name="Work", last_name="Doer")

        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_usernames": "workdoer",  # Use username from chip input
                "text": "Work performed by someone else",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()

        self.assertEqual(log_entry.created_by, self.maintainer_user)
        self.assertIn(Maintainer.objects.get(user=work_doer), log_entry.maintainers.all())


@tag("views")
class LogEntryProblemReportTests(TestDataMixin, TestCase):
    """Tests for creating log entries from problem reports."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.ProblemType.STUCK_BALL,
            description="Ball stuck in the playfield",
        )
        self.create_url = reverse(
            "log-create-problem-report", kwargs={"pk": self.problem_report.pk}
        )

    def test_create_view_accessible_to_staff(self):
        """Staff users should be able to access the log entry create form from problem report."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/log_entry_new.html")

    def test_create_view_shows_problem_report_context(self):
        """Create form should show the problem report context."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)

        # Sidebar shows "Problem" label with linked problem card
        self.assertContains(response, "sidebar-card--problem")
        self.assertContains(response, self.machine.name)

    def test_create_log_entry_inherits_machine_from_problem_report(self):
        """Log entry created from problem report should inherit the machine."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Investigated the stuck ball issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.machine, self.machine)

    def test_create_log_entry_links_to_problem_report(self):
        """Log entry created from problem report should be linked to the problem report."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Fixed the stuck ball",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.problem_report, self.problem_report)

    def test_create_log_entry_redirects_to_problem_report(self):
        """After creating log entry from problem report, should redirect back to problem report."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Fixed the issue",
            },
        )

        expected_url = reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk})
        self.assertRedirects(response, expected_url)

    def test_regular_log_entry_has_no_problem_report(self):
        """Log entries created from machine context should not have a problem_report."""
        self.client.force_login(self.maintainer_user)
        regular_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

        response = self.client.post(
            regular_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Regular maintenance",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertIsNone(log_entry.problem_report)

    def test_close_problem_checkbox_closes_problem_report(self):
        """Checking 'close the problem report' should close it when creating log entry."""
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Fixed the stuck ball",
                "close_problem": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.Status.CLOSED)

    def test_without_close_problem_checkbox_leaves_problem_open(self):
        """Not checking 'close the problem report' should leave it open."""
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Investigated the issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)


@tag("views")
class MachineLogCreateViewIdempotencyTests(TestDataMixin, TestCase):
    """The submission_id token collapses retried submissions into one entry."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})
        self.client.force_login(self.maintainer_user)

    def _payload(self, token, text="Adjusted the flippers"):
        return {
            "submission_id": str(token),
            "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
            "maintainer_freetext": "Test User",
            "text": text,
        }

    def test_resubmitting_same_token_does_not_duplicate(self):
        """The same rendered form submitted twice creates only one entry."""
        token = uuid4()

        first = self.client.post(self.create_url, self._payload(token))
        second = self.client.post(self.create_url, self._payload(token))

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertEqual(LogEntry.objects.get().submission_id, token)

    def test_different_tokens_create_separate_entries(self):
        """Two different people (different tokens) both get their entries kept."""
        self.client.post(self.create_url, self._payload(uuid4()))
        self.client.post(self.create_url, self._payload(uuid4()))

        self.assertEqual(LogEntry.objects.count(), 2)

    def test_missing_token_still_creates_entry(self):
        """A submission without a token falls back to an unconditional create."""
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "No token here",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertIsNone(LogEntry.objects.get().submission_id)

    def test_get_form_seeds_a_submission_token(self):
        """The rendered form carries a fresh hidden submission_id."""
        response = self.client.get(self.create_url)
        self.assertContains(response, 'name="submission_id"')

    def test_token_from_a_different_entry_is_rejected(self):
        """A token already tied to another entry is rejected, not silently swallowed."""
        from flipfix.apps.core.test_utils import create_machine

        other_machine = create_machine(name="Other Machine")
        token = uuid4()
        LogEntry.objects.create(
            machine=other_machine,
            text="prior work",
            submission_id=token,
            created_by=self.maintainer_user,
        )

        response = self.client.post(self.create_url, self._payload(token))

        self.assertEqual(response.status_code, 200)  # re-rendered form, not a redirect
        self.assertContains(response, "already used for a different entry")
        self.assertEqual(LogEntry.objects.filter(machine=self.machine).count(), 0)

    def test_duplicate_takes_the_already_recorded_path(self):
        """The retry hits the duplicate branch (info message), not a second create."""
        token = uuid4()

        first = self.client.post(self.create_url, self._payload(token), follow=True)
        second = self.client.post(self.create_url, self._payload(token), follow=True)

        self.assertContains(first, "Log entry added")
        self.assertNotContains(first, "already recorded")
        self.assertContains(second, "That log entry was already recorded.")
        self.assertEqual(LogEntry.objects.count(), 1)


@tag("views")
class LogEntryMultiMaintainerTests(TestDataMixin, TestCase):
    """Tests for multi-maintainer chip input functionality."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})
        self.maintainer2 = create_maintainer_user(
            username="maintainer2", first_name="Second", last_name="Maintainer"
        )
        self.maintainer3 = create_maintainer_user(
            username="maintainer3", first_name="Third", last_name="Maintainer"
        )

    def test_create_with_multiple_maintainers(self):
        """Can create log entry with multiple linked maintainers."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_usernames": [
                    self.maintainer_user.username,
                    self.maintainer2.username,
                ],
                "text": "Work done by two people",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 2)
        self.assertIn(
            Maintainer.objects.get(user=self.maintainer_user), log_entry.maintainers.all()
        )
        self.assertIn(Maintainer.objects.get(user=self.maintainer2), log_entry.maintainers.all())

    def test_create_with_freetext_name(self):
        """Can create log entry with freetext maintainer name."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "John Doe",
                "text": "Work done by external person",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 0)
        self.assertEqual(log_entry.maintainer_names, "John Doe")

    def test_create_with_mixed_maintainers_and_freetext(self):
        """Can create log entry with both linked maintainers and freetext names."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_usernames": self.maintainer_user.username,
                "maintainer_freetext": ["External Helper", "Another Person"],
                "text": "Team effort",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 1)
        self.assertEqual(log_entry.maintainer_names, "External Helper, Another Person")

    def test_create_deduplicates_freetext_names(self):
        """Duplicate freetext names are deduplicated."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": ["John Doe", "John Doe", "Jane Doe"],
                "text": "Work done",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        # Duplicates should be removed
        self.assertEqual(log_entry.maintainer_names, "John Doe, Jane Doe")

    def test_create_with_no_maintainer_uses_current_user(self):
        """Regular user with no maintainer selection defaults to current user."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "text": "Work performed",
                # No maintainer_usernames or maintainer_freetext
            },
        )

        # Should succeed and default to current user
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 1)
        self.assertIn(
            Maintainer.objects.get(user=self.maintainer_user),
            log_entry.maintainers.all(),
        )


@tag("views")
class LogEntrySharedAccountTests(
    SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for log entry creation from shared/terminal accounts."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_shared_account_with_valid_username_uses_maintainer(self):
        """Shared account selecting from chip input saves to M2M."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_usernames": self.identifying_user.username,
                "text": "Work done by identified user",
            },
        )
        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 1)
        self.assertIn(self.identifying_maintainer, log_entry.maintainers.all())

    def test_shared_account_with_free_text_uses_text_field(self):
        """Shared account typing free text saves to maintainer_names field."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Jane Visitor",
                "text": "Work done by external person",
            },
        )
        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 0)
        self.assertEqual(log_entry.maintainer_names, "Jane Visitor")

    def test_shared_account_with_empty_maintainer_shows_error(self):
        """Shared account with no maintainer selection shows form error."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "text": "Work done",
                # No maintainer_usernames or maintainer_freetext
            },
        )
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertContains(response, "Please add at least one maintainer")
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_regular_account_with_no_maintainer_uses_current_user(self):
        """Regular account with no maintainer selection defaults to current user."""
        self.client.force_login(self.identifying_user)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "text": "Work done",
                # No maintainer_usernames or maintainer_freetext
            },
        )
        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.maintainers.count(), 1)
        self.assertIn(self.identifying_maintainer, log_entry.maintainers.all())
