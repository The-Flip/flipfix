"""Tests for wiki reorder view and API."""

import json

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.models import WikiPage, WikiPageTag, WikiTagOrder


@tag("views")
class WikiReorderViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiReorderView (the page itself)."""

    def test_reorder_page_returns_200(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("wiki-reorder"))
        self.assertEqual(response.status_code, 200)

    def test_reorder_page_requires_login(self):
        response = self.client.get(reverse("wiki-reorder"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_reorder_page_requires_maintainer_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("wiki-reorder"))
        self.assertEqual(response.status_code, 403)

    def test_reorder_page_shows_pages(self):
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test Page", slug="test-page")
        response = self.client.get(reverse("wiki-reorder"))
        self.assertContains(response, "Test Page")


@tag("views")
class WikiReorderSaveTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiReorderSaveView (the API endpoint)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("api-wiki-reorder")
        self.client.force_login(self.maintainer_user)

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_save_page_order(self):
        WikiPage.objects.create(title="Alpha", slug="alpha")
        WikiPage.objects.create(title="Beta", slug="beta")
        # Signal auto-creates untagged sentinel tags

        response = self._post(
            {
                "pages": [
                    {"tag": "", "slug": "beta", "order": 0},
                    {"tag": "", "slug": "alpha", "order": 1},
                ],
                "tags": [],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.assertEqual(WikiPageTag.objects.get(tag="", slug="beta").order, 0)
        self.assertEqual(WikiPageTag.objects.get(tag="", slug="alpha").order, 1)

    def test_save_tag_order(self):
        page1 = WikiPage.objects.create(title="P1", slug="p1")
        WikiPageTag.objects.create(page=page1, tag="zebra", slug="p1")
        page2 = WikiPage.objects.create(title="P2", slug="p2")
        WikiPageTag.objects.create(page=page2, tag="alpha", slug="p2")

        response = self._post(
            {
                "pages": [],
                "tags": [
                    {"tag": "zebra", "order": 0},
                    {"tag": "alpha", "order": 1},
                ],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WikiTagOrder.objects.get(tag="zebra").order, 0)
        self.assertEqual(WikiTagOrder.objects.get(tag="alpha").order, 1)

    def test_save_updates_existing_tag_order(self):
        WikiTagOrder.objects.create(tag="machines", order=99)

        response = self._post(
            {
                "pages": [],
                "tags": [{"tag": "machines", "order": 0}],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WikiTagOrder.objects.get(tag="machines").order, 0)

    def test_save_combined_page_and_tag_order(self):
        page = WikiPage.objects.create(title="Doc", slug="doc")
        WikiPageTag.objects.create(page=page, tag="guides", slug="doc")

        response = self._post(
            {
                "pages": [{"tag": "guides", "slug": "doc", "order": 0}],
                "tags": [{"tag": "guides", "order": 5}],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WikiPageTag.objects.get(tag="guides", slug="doc").order, 0)
        self.assertEqual(WikiTagOrder.objects.get(tag="guides").order, 5)

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            self.url,
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_requires_login(self):
        from django.test import Client

        anon = Client()
        response = anon.post(
            self.url,
            data=json.dumps({"pages": [], "tags": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_requires_maintainer_access(self):
        self.client.force_login(self.regular_user)
        response = self._post({"pages": [], "tags": []})
        self.assertEqual(response.status_code, 403)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_empty_payload_succeeds(self):
        response = self._post({"pages": [], "tags": []})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_malformed_page_items_returns_400(self):
        response = self._post({"pages": [{"wrong": "keys"}], "tags": []})
        self.assertEqual(response.status_code, 400)

    def test_non_dict_items_returns_400(self):
        response = self._post({"pages": ["not-a-dict"], "tags": []})
        self.assertEqual(response.status_code, 400)
