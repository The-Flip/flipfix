"""Tests for the machine Explore (collection visualization) view."""

from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import MachineInstance, MachineModel
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_user,
)


@tag("views")
class MachineExploreViewAccessTests(AccessControlTestCase):
    """Access control for the public Explore route."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.url = reverse("machine-explore")

    def test_anonymous_redirected_to_login(self):
        """Guests are redirected when guest access is disabled (the default)."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_non_maintainer_can_view_public_route(self):
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_maintainer_can_view(self):
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)


@tag("views")
class MachineExploreViewDataTests(TestCase):
    """The chart payload reflects owned machines and excludes incomplete data."""

    def setUp(self):
        self.client.force_login(create_maintainer_user())
        self.url = reverse("machine-explore")

    def _chart(self):
        return self.client.get(self.url).context

    def test_one_dot_per_instance(self):
        """Two physical copies of one model produce two dots."""
        model = create_machine_model(manufacturer="Williams", year=1992, era=MachineModel.Era.SS)
        create_machine(model=model, slug="twi-1", name="Twilight Zone #1")
        create_machine(model=model, slug="twi-2", name="Twilight Zone #2")

        chart_data = self._chart()["chart_data"]
        self.assertEqual(len(chart_data), 2)
        self.assertTrue(
            all(d["manufacturer"] == "Williams" and d["year"] == 1992 for d in chart_data)
        )

    def test_payload_fields_and_labels(self):
        model = create_machine_model(manufacturer="Bally", year=1980, era=MachineModel.Era.EM)
        create_machine(
            model=model,
            slug="kiss",
            name="Kiss",
            operational_status=MachineInstance.OperationalStatus.BROKEN,
        )

        dot = self._chart()["chart_data"][0]
        self.assertEqual(dot["name"], "Kiss")
        self.assertEqual(dot["era"], "EM")
        self.assertEqual(dot["era_label"], "Electromechanical")
        self.assertEqual(dot["status_label"], "Broken")
        self.assertEqual(dot["url"], reverse("maintainer-machine-detail", args=["kiss"]))

    def test_excludes_instances_missing_year_or_manufacturer(self):
        """Machines missing year or manufacturer are not charted (era is inferable)."""
        create_machine(
            model=create_machine_model(manufacturer="Gottlieb", year=1975, era=MachineModel.Era.EM)
        )
        create_machine(model=create_machine_model(year=None), slug="no-year")
        create_machine(model=create_machine_model(manufacturer=""), slug="no-mfr")
        # Blank era but a known year is now inferred (plotted), not excluded.
        create_machine(model=create_machine_model(year=2001, era=""), slug="no-era")

        context = self._chart()
        self.assertEqual(len(context["chart_data"]), 2)  # Gottlieb + inferred-era machine
        self.assertEqual(context["excluded_count"], 2)  # no-year, no-mfr
        self.assertEqual(len(context["excluded"]), 2)

    def test_excluded_entries_name_the_missing_dimensions(self):
        """Each excluded entry links to the machine and lists what it's missing."""
        create_machine(
            model=create_machine_model(name="No Year", year=None, era=MachineModel.Era.SS),
            name="No Year",
            slug="no-year",
        )
        create_machine(
            model=create_machine_model(name="Bare", year=None, manufacturer="", era=""),
            name="Bare",
            slug="bare",
        )

        excluded = {m["name"]: m for m in self._chart()["excluded"]}
        self.assertEqual(excluded["No Year"]["missing"], ["year"])
        self.assertEqual(excluded["Bare"]["missing"], ["year", "manufacturer", "era"])
        self.assertEqual(
            excluded["No Year"]["url"], reverse("maintainer-machine-detail", args=["no-year"])
        )

    def test_missing_era_is_inferred_from_year(self):
        """A machine with year + manufacturer but no era is plotted via inferred era."""
        create_machine(
            model=create_machine_model(manufacturer="Gottlieb", year=1965, era=""),
            name="Eraless EM",
            slug="eraless",
        )

        context = self._chart()
        self.assertEqual(context["excluded"], [])
        self.assertEqual(len(context["chart_data"]), 1)
        dot = context["chart_data"][0]
        self.assertEqual(dot["era"], MachineModel.Era.EM)
        self.assertEqual(dot["era_label"], "Electromechanical")

    def test_no_excluded_when_all_plottable(self):
        create_machine(
            model=create_machine_model(manufacturer="Bally", year=1980, era=MachineModel.Era.EM)
        )
        context = self._chart()
        self.assertEqual(context["excluded"], [])
        self.assertEqual(context["excluded_count"], 0)

    def test_legend_lists_all_eras(self):
        legend = self._chart()["legend"]
        self.assertEqual(
            [item["era"] for item in legend],
            [MachineModel.Era.PM, MachineModel.Era.EM, MachineModel.Era.SS],
        )
