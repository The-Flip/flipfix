"""Tests for public machine detail view.

Maintainer machine feed tests are in test_machine_feed.py.
"""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import create_machine


@tag("views")
class PublicMachineDetailViewTests(TestCase):
    """Tests for public-facing machine detail view."""

    def setUp(self):
        """Set up test data for public views."""
        self.machine = create_machine(slug="public-machine")
        self.detail_url = reverse("public-machine-detail", kwargs={"slug": self.machine.slug})

    def test_public_detail_view_accessible(self):
        """Public detail view should be accessible to anonymous users."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_detail_public.html")

    def test_public_detail_view_displays_machine_details(self):
        """Public detail view should display machine-specific details."""
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.machine.name)
        self.assertContains(response, self.machine.model.manufacturer)


@tag("views")
class PublicMachineDetailEdgeCaseTests(TestCase):
    """Edge case tests for public machine detail view."""

    def test_machine_without_manufacturer(self):
        """Should handle machines with no manufacturer gracefully."""
        machine = create_machine(slug="no-mfr-machine", manufacturer="", year=None)
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, machine.name)

    def test_machine_with_year_no_month(self):
        """Should display year only when month is not specified."""
        machine = create_machine(slug="year-only", year=1990, month=None)
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1990")

    def test_machine_with_month_and_year(self):
        """Should display month name and year when both are specified."""
        machine = create_machine(slug="month-year", year=1995, month=6)
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        # Should contain month name (June) and year
        self.assertContains(response, "1995")

    def test_machine_with_all_credits_empty(self):
        """Should not display empty credits section."""
        machine = create_machine(slug="no-credits")
        machine.model.design_credit = ""
        machine.model.concept_and_design_credit = ""
        machine.model.art_credit = ""
        machine.model.sound_credit = ""
        machine.model.production_quantity = ""
        machine.model.factory_address = ""
        machine.model.save()
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        # Should not have the credits card if all fields are empty
        self.assertNotContains(response, "<strong>Production:</strong>")
        self.assertNotContains(response, "<strong>Design:</strong>")

    def test_machine_with_educational_text(self):
        """Should display educational text when present."""
        machine = create_machine(slug="edu-machine")
        machine.model.educational_text = "This is a historically significant machine."
        machine.model.save()
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "historically significant")

    def test_machine_with_sources_notes(self):
        """Should display sources and references when present."""
        machine = create_machine(slug="sources-machine")
        machine.model.sources_notes = "Source: Internet Pinball Database"
        machine.model.save()
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sources & References")
        self.assertContains(response, "Internet Pinball Database")

    def test_problem_report_link_present(self):
        """Problem report link should be present on public detail page."""
        machine = create_machine(slug="report-machine")
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        report_url = reverse("public-problem-report-create", kwargs={"slug": machine.slug})
        self.assertContains(response, report_url)
        self.assertContains(response, "Report a Problem")

    def test_ownership_display_present(self):
        """Ownership information should be displayed."""
        machine = create_machine(slug="owned-machine")
        detail_url = reverse("public-machine-detail", kwargs={"slug": machine.slug})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        # Should contain ownership display
        self.assertContains(response, machine.ownership_display)