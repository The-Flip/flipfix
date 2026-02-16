"""Tests for wiki page detail view."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import RecordReference
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.models import WikiPage, WikiPageTag


@tag("views")
class WikiPageDetailViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiPageDetailView."""

    def test_detail_view_returns_200(self):
        """Valid page path returns 200."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="Test Page", slug="test-page")
        WikiPageTag.objects.create(page=page, tag="docs", slug="test-page")

        response = self.client.get(reverse("wiki-page-detail", args=["docs/test-page"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Page")

    def test_detail_view_untagged_page(self):
        """Untagged page (empty tag) returns 200."""
        self.client.force_login(self.maintainer_user)

        # Signal auto-creates untagged sentinel
        WikiPage.objects.create(title="Root Page", slug="root-page")

        response = self.client.get(reverse("wiki-page-detail", args=["root-page"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Root Page")

    def test_detail_view_nested_tag(self):
        """Nested tag path returns 200."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="Nested", slug="nested")
        WikiPageTag.objects.create(page=page, tag="machines/blackout", slug="nested")

        response = self.client.get(reverse("wiki-page-detail", args=["machines/blackout/nested"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nested")

    def test_detail_view_missing_page_returns_404(self):
        """Non-existent page returns 404."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-page-detail", args=["does/not/exist"]))

        self.assertEqual(response.status_code, 404)

    def test_detail_view_requires_login(self):
        """Unauthenticated users are redirected to login."""
        # Signal auto-creates untagged sentinel
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-detail", args=["test"]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_detail_view_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)

        # Signal auto-creates untagged sentinel
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-detail", args=["test"]))

        self.assertEqual(response.status_code, 403)

    def test_detail_view_contains_top_edit_link(self):
        """The breadcrumb bar contains an Edit link to the page edit URL."""
        self.client.force_login(self.maintainer_user)

        page = WikiPage.objects.create(title="Test Page", slug="test-page")
        WikiPageTag.objects.create(page=page, tag="docs", slug="test-page")

        response = self.client.get(reverse("wiki-page-detail", args=["docs/test-page"]))

        edit_url = reverse("wiki-page-edit", args=["docs/test-page"])
        self.assertContains(response, f'href="{edit_url}"')
        self.assertContains(response, "breadcrumb-bar__action")


@tag("views")
class WikiPageDetailRedirectTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for 301 redirect from old /wiki/doc/ URLs to new /doc/ URLs."""

    def test_old_wiki_doc_url_redirects_permanently(self):
        """Old /wiki/doc/ URL returns 301 to /doc/."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test", slug="test-page")

        response = self.client.get("/wiki/doc/test-page")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/doc/test-page")

    def test_old_wiki_doc_url_redirects_nested_path(self):
        """Old /wiki/doc/ redirect preserves full nested path."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get("/wiki/doc/machines/blackout/system-6")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/doc/machines/blackout/system-6")


@tag("views")
class WikiPageCheckboxToggleTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for inline checkbox toggling via AJAX POST."""

    def setUp(self):
        super().setUp()
        self.page = WikiPage.objects.create(
            title="Checklist",
            slug="checklist",
            content="- [ ] Item 1\n- [ ] Item 2",
        )
        # Signal auto-creates untagged sentinel WikiPageTag
        self.url = reverse("wiki-page-detail", args=["checklist"])

    def test_update_text_saves_content(self):
        """POST update_text saves new content."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": "- [x] Item 1\n- [ ] Item 2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.page.refresh_from_db()
        self.assertEqual(self.page.content, "- [x] Item 1\n- [ ] Item 2")

    def test_update_text_sets_updated_by(self):
        """POST update_text sets updated_by to the current user."""
        self.client.force_login(self.maintainer_user)

        self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": "- [x] Done",
            },
        )

        self.page.refresh_from_db()
        self.assertEqual(self.page.updated_by, self.maintainer_user)

    def test_update_text_converts_authoring_links(self):
        """POST update_text converts authoring-format links to storage format."""
        self.client.force_login(self.maintainer_user)
        machine = MachineInstance.objects.first()

        self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": f"See [[machine:{machine.slug}]]",
            },
        )

        self.page.refresh_from_db()
        self.assertIn(f"[[machine:id:{machine.pk}]]", self.page.content)

    def test_update_text_syncs_references(self):
        """POST update_text syncs RecordReference records."""
        self.client.force_login(self.maintainer_user)
        machine = MachineInstance.objects.first()

        self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": f"See [[machine:{machine.slug}]]",
            },
        )

        ct = ContentType.objects.get_for_model(WikiPage)
        self.assertTrue(
            RecordReference.objects.filter(source_type=ct, source_id=self.page.pk).exists()
        )

    def test_update_text_broken_link_returns_400(self):
        """POST update_text with a non-existent link target returns 400."""
        self.client.force_login(self.maintainer_user)
        original_content = self.page.content

        response = self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": "See [[machine:does-not-exist]]",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.page.refresh_from_db()
        self.assertEqual(self.page.content, original_content)

    def test_unknown_action_returns_400(self):
        """POST with unknown action returns 400."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(self.url, {"action": "bogus"})

        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_post_redirects(self):
        """Unauthenticated POST redirects to login."""
        response = self.client.post(
            self.url,
            {
                "action": "update_text",
                "text": "sneaky",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
