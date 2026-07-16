"""Tests for the maintainer-only daily report landing page."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
    TestDataMixin,
    create_location,
    create_log_entry,
    create_machine,
    create_machine_model,
    create_problem_report,
)
from flipfix.apps.maintenance.models import ProblemReport

S = MachineInstance.OperationalStatus
P = ProblemReport.Priority
Z = Location.Zone


@tag("views")
class DailyReportViewTests(TestDataMixin, TestCase):
    url = reverse("daily-maintenance-report")

    def setUp(self):
        super().setUp()
        self.front = create_location("Coin-Op", Z.FRONT)
        self.workshop = create_location("Workshop", Z.WORKSHOP)

    def test_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_maintainer_gets_200(self):
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_machine_links_to_detail(self):
        m = create_machine(location=self.front, model=create_machine_model())
        self.client.force_login(self.maintainer_user)
        resp = self.client.get(self.url)
        self.assertContains(resp, reverse("maintainer-machine-detail", args=[m.slug]))

    def test_down_machine_links_to_its_report(self):
        m = create_machine(
            location=self.workshop, operational_status=S.BROKEN, model=create_machine_model()
        )
        pr = create_problem_report(
            machine=m, priority=P.UNPLAYABLE, status=ProblemReport.Status.OPEN
        )
        self.client.force_login(self.maintainer_user)
        resp = self.client.get(self.url)
        self.assertContains(resp, reverse("problem-report-detail", args=[pr.id]))

    def test_fixing_duration_links_to_log_entry(self):
        m = create_machine(
            location=self.workshop, operational_status=S.FIXING, model=create_machine_model()
        )
        log = create_log_entry(machine=m, occurred_at=timezone.now() - timedelta(days=1))
        self.client.force_login(self.maintainer_user)
        resp = self.client.get(self.url)
        self.assertContains(resp, reverse("log-detail", args=[log.id]))

    def test_hidden_zone_machine_not_rendered(self):
        hidden = create_location("Basement", Z.HIDDEN)
        create_machine(location=hidden, name="SecretMachine", model=create_machine_model())
        self.client.force_login(self.maintainer_user)
        resp = self.client.get(self.url)
        self.assertNotContains(resp, "SecretMachine")
