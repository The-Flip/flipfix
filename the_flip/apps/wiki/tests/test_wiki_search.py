"""Tests for wiki search view."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.models import WikiPage, WikiPageTag


@tag("views")
class WikiSearchViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiSearchView."""

    def test_search_returns_200(self):
        """Search page returns 200."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-search"))

        self.assertEqual(response.status_code, 200)

    def test_search_finds_by_title(self):
        """Search finds pages by title."""
        self.client.force_login(self.maintainer_user)

        # Signal auto-creates untagged sentinel
        WikiPage.objects.create(title="Unique Title", slug="unique")

        response = self.client.get(reverse("wiki-search") + "?q=Unique")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unique Title")

    def test_search_finds_by_content(self):
        """Search finds pages by content."""
        self.client.force_login(self.maintainer_user)

        # Signal auto-creates untagged sentinel
        WikiPage.objects.create(title="Page", slug="page", content="Special content here")

        response = self.client.get(reverse("wiki-search") + "?q=Special")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Page")

    def test_search_finds_by_tag(self):
        """Search finds pages by tag name."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="Tagged", slug="tagged")
        WikiPageTag.objects.create(page=page, tag="machines/blackout", slug="tagged")

        response = self.client.get(reverse("wiki-search") + "?q=blackout")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tagged")

    def test_search_empty_query_shows_nothing(self):
        """Empty search query shows no results."""
        self.client.force_login(self.maintainer_user)

        WikiPage.objects.create(title="Page", slug="page")

        response = self.client.get(reverse("wiki-search") + "?q=")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Found")
        self.assertEqual(list(response.context["pages"]), [])

    def test_search_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(reverse("wiki-search"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
