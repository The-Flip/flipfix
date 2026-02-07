"""Tests for link targets and link types API endpoints."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate
from the_flip.apps.wiki.models import WikiPage, WikiPageTag


@tag("views")
class LinkTypesAPITests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LinkTypesView API endpoint."""

    def setUp(self):
        super().setUp()
        self.url = reverse("api-link-types")

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_returns_types_list(self):
        """Returns list of available link types."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("types", data)
        self.assertGreater(len(data["types"]), 0)

    def test_types_have_required_fields(self):
        """Each type has name, label, and description."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url)

        data = response.json()
        for t in data["types"]:
            self.assertIn("name", t)
            self.assertIn("label", t)
            self.assertIn("description", t)

    def test_types_include_all_registered(self):
        """All registered link types with autocomplete support are included."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url)

        data = response.json()
        names = [t["name"] for t in data["types"]]
        for expected in ["page", "machine", "model", "problem", "log", "partrequest"]:
            self.assertIn(expected, names)


@tag("views")
class LinkTargetsAPITests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LinkTargetsView API endpoint."""

    def setUp(self):
        super().setUp()
        self.url = reverse("api-link-targets")

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.url + "?type=page")

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_invalid_type_returns_400(self):
        """Invalid type parameter returns 400 error."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url + "?type=invalid")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    def test_missing_type_returns_400(self):
        """Missing type parameter returns 400 error."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)

    def test_page_type_returns_pages(self):
        """Type=page returns wiki pages."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="Test Page", slug="test-page")
        # Signal creates untagged sentinel, add a tagged one too
        WikiPageTag.objects.create(page=page, tag="machines", slug="test-page")

        response = self.client.get(self.url + "?type=page")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        # Should have results (at least the tagged one we created)
        self.assertGreater(len(data["results"]), 0)

    def test_page_type_search_filters_by_title(self):
        """Type=page with q filters by title."""
        self.client.force_login(self.maintainer_user)

        WikiPage.objects.create(title="Blackout Guide", slug="blackout")
        WikiPage.objects.create(title="Other Page", slug="other")

        response = self.client.get(self.url + "?type=page&q=blackout")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should find Blackout but not Other
        labels = [r["label"] for r in data["results"]]
        self.assertIn("Blackout Guide", labels)
        self.assertNotIn("Other Page", labels)

    def test_machine_type_returns_machines(self):
        """Type=machine returns machine instances."""
        self.client.force_login(self.maintainer_user)

        # Use existing test machine from TestDataMixin
        response = self.client.get(self.url + "?type=machine")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

    def test_machine_type_search_filters_by_name(self):
        """Type=machine with q filters by machine name."""
        self.client.force_login(self.maintainer_user)

        # Create a second machine to test filtering
        model2 = MachineModel.objects.create(name="Different Model", slug="different")
        MachineInstance.objects.create(name="Different Machine", slug="different", model=model2)

        response = self.client.get(self.url + f"?type=machine&q={self.machine.name}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        refs = [r["ref"] for r in data["results"]]
        self.assertIn(self.machine.slug, refs)

    def test_model_type_returns_models(self):
        """Type=model returns machine models."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url + "?type=model")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

    def test_model_type_search_filters_by_name(self):
        """Type=model with q filters by model name."""
        self.client.force_login(self.maintainer_user)

        MachineModel.objects.create(name="Gorgar", slug="gorgar", manufacturer="Williams")
        MachineModel.objects.create(name="Firepower", slug="firepower", manufacturer="Williams")

        response = self.client.get(self.url + "?type=model&q=Gorgar")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        refs = [r["ref"] for r in data["results"]]
        self.assertIn("gorgar", refs)
        self.assertNotIn("firepower", refs)

    def test_page_results_include_path_as_ref(self):
        """Page results include the full path in ref for link syntax."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="System 6", slug="system-6")
        WikiPageTag.objects.create(page=page, tag="machines/blackout", slug="system-6")

        response = self.client.get(self.url + "?type=page&q=system")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Find the tagged result
        tagged = next(
            (r for r in data["results"] if r["ref"] == "machines/blackout/system-6"),
            None,
        )
        self.assertIsNotNone(tagged)
        self.assertEqual(tagged["label"], "System 6")
        self.assertEqual(tagged["path"], "machines/blackout")

    def test_machine_results_include_manufacturer_year(self):
        """Machine results include manufacturer and year in label."""
        self.client.force_login(self.maintainer_user)

        model = MachineModel.objects.create(
            name="Test Model", slug="test-model", manufacturer="Williams", year=1980
        )
        MachineInstance.objects.create(name="Test Instance", slug="test-instance", model=model)

        response = self.client.get(self.url + "?type=machine&q=test-instance")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = next((r for r in data["results"] if r["ref"] == "test-instance"), None)
        self.assertIsNotNone(result)
        self.assertIn("Williams", result["label"])
        self.assertIn("1980", result["label"])

    def test_empty_query_returns_all(self):
        """Empty q parameter returns all results (up to limit)."""
        self.client.force_login(self.maintainer_user)

        # Create a few pages
        for i in range(3):
            WikiPage.objects.create(title=f"Page {i}", slug=f"page-{i}")

        response = self.client.get(self.url + "?type=page&q=")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should return multiple results
        self.assertGreater(len(data["results"]), 1)

    def test_results_limited_to_50(self):
        """Results are capped at 50 items with total_count showing true count."""
        self.client.force_login(self.maintainer_user)

        # Create 60 models to exceed the limit
        for i in range(60):
            MachineModel.objects.create(name=f"Model {i:02d}", slug=f"model-{i:02d}")

        response = self.client.get(self.url + "?type=model&q=")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 50)
        # total_count reflects the full queryset, not the truncated results
        self.assertGreater(data["total_count"], 50)

    def test_total_count_matches_results_when_under_limit(self):
        """total_count equals result count when all results fit within the limit."""
        self.client.force_login(self.maintainer_user)

        WikiPage.objects.create(title="Unique Page XYZ", slug="unique-xyz")

        response = self.client.get(self.url + "?type=page&q=Unique Page XYZ")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_count"], len(data["results"]))

    def test_search_with_special_characters(self):
        """Search handles special characters without error."""
        self.client.force_login(self.maintainer_user)

        # Create page with special chars in title
        WikiPage.objects.create(title="Test & Demo <Page>", slug="test-demo")

        # Search with special characters - should not crash
        response = self.client.get(self.url + "?type=page&q=%26%3C%3E")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)

    def test_search_with_unicode(self):
        """Search handles unicode characters."""
        self.client.force_login(self.maintainer_user)

        WikiPage.objects.create(title="Pinball Café Guide", slug="cafe-guide")

        response = self.client.get(self.url + "?type=page&q=Café")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        labels = [r["label"] for r in data["results"]]
        self.assertIn("Pinball Café Guide", labels)

    def test_search_is_case_insensitive(self):
        """Search is case-insensitive."""
        self.client.force_login(self.maintainer_user)

        WikiPage.objects.create(title="BLACKOUT Guide", slug="blackout")

        # Search with lowercase
        response = self.client.get(self.url + "?type=page&q=blackout")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        labels = [r["label"] for r in data["results"]]
        self.assertIn("BLACKOUT Guide", labels)

    def test_model_search_by_manufacturer(self):
        """Model search also matches manufacturer name."""
        self.client.force_login(self.maintainer_user)

        MachineModel.objects.create(name="Firepower", slug="firepower", manufacturer="Williams")
        MachineModel.objects.create(name="Orbitor 1", slug="orbitor", manufacturer="Stern")

        response = self.client.get(self.url + "?type=model&q=Williams")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        refs = [r["ref"] for r in data["results"]]
        self.assertIn("firepower", refs)
        self.assertNotIn("orbitor", refs)

    # ------------------------------------------------------------------
    # ID-based types: problem, log, partrequest, partrequestupdate
    # ------------------------------------------------------------------

    def test_problem_type_returns_problems(self):
        """Type=problem returns problem reports."""
        self.client.force_login(self.maintainer_user)

        ProblemReport.objects.create(machine=self.machine, description="Flipper stuck")

        response = self.client.get(self.url + "?type=problem")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)
        # Results should include a ref field
        self.assertIn("ref", data["results"][0])

    def test_problem_type_search_filters(self):
        """Type=problem with q filters by description."""
        self.client.force_login(self.maintainer_user)

        pr1 = ProblemReport.objects.create(machine=self.machine, description="Flipper stuck")
        ProblemReport.objects.create(machine=self.machine, description="No credits")

        response = self.client.get(self.url + "?type=problem&q=Flipper")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        refs = [r["ref"] for r in data["results"]]
        self.assertIn(str(pr1.id), refs)
        self.assertEqual(len(refs), 1)

    def test_log_type_returns_log_entries(self):
        """Type=log returns log entries."""
        self.client.force_login(self.maintainer_user)

        LogEntry.objects.create(machine=self.machine, text="Replaced flipper rubber")

        response = self.client.get(self.url + "?type=log")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)
        self.assertIn("ref", data["results"][0])

    def test_log_type_search_filters(self):
        """Type=log with q filters by text."""
        self.client.force_login(self.maintainer_user)

        LogEntry.objects.create(machine=self.machine, text="Replaced flipper rubber")
        LogEntry.objects.create(machine=self.machine, text="Cleaned playfield")

        response = self.client.get(self.url + "?type=log&q=flipper")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        labels = " ".join(r["label"] for r in data["results"])
        self.assertIn("flipper", labels.lower())

    def test_partrequest_type_returns_part_requests(self):
        """Type=partrequest returns part requests."""
        self.client.force_login(self.maintainer_user)

        PartRequest.objects.create(text="Need new flipper bat")

        response = self.client.get(self.url + "?type=partrequest")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)
        self.assertIn("ref", data["results"][0])

    def test_partrequest_type_search_filters(self):
        """Type=partrequest with q filters by text."""
        self.client.force_login(self.maintainer_user)

        PartRequest.objects.create(text="Need new flipper bat")
        PartRequest.objects.create(text="Order replacement bulbs")

        response = self.client.get(self.url + "?type=partrequest&q=flipper")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        labels = " ".join(r["label"] for r in data["results"])
        self.assertIn("flipper", labels.lower())

    def test_partrequestupdate_type_returns_updates(self):
        """Type=partrequestupdate returns update with text preview in label."""
        self.client.force_login(self.maintainer_user)

        pr = PartRequest.objects.create(text="Need new flipper bat")
        update = PartRequestUpdate.objects.create(part_request=pr, text="Ordered parts")

        response = self.client.get(self.url + "?type=partrequestupdate")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)
        label = data["results"][0]["label"]
        self.assertIn(f"#{update.pk}", label)
        self.assertIn(f"#{pr.pk}", label)
        self.assertIn("Ordered parts", label)

    def test_partrequestupdate_label_truncates_long_text(self):
        """Type=partrequestupdate truncates text preview to 20 characters."""
        self.client.force_login(self.maintainer_user)

        pr = PartRequest.objects.create(text="Need parts")
        PartRequestUpdate.objects.create(
            part_request=pr, text="This is a very long update text that should be truncated"
        )

        response = self.client.get(self.url + "?type=partrequestupdate")

        data = response.json()
        label = data["results"][0]["label"]
        # Should contain first 20 chars of text, not the full text
        self.assertIn("This is a very long ", label)
        self.assertNotIn("truncated", label)

    def test_partrequestupdate_type_search_filters(self):
        """Type=partrequestupdate with q filters by text."""
        self.client.force_login(self.maintainer_user)

        pr = PartRequest.objects.create(text="Need parts")
        PartRequestUpdate.objects.create(part_request=pr, text="Ordered from supplier")
        PartRequestUpdate.objects.create(part_request=pr, text="Shipped today")

        response = self.client.get(self.url + "?type=partrequestupdate&q=supplier")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)

    def test_results_have_label_and_ref(self):
        """All results include label and ref fields."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url + "?type=machine")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        for result in data["results"]:
            self.assertIn("label", result)
            self.assertIn("ref", result)
