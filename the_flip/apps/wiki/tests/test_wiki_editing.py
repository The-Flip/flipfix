"""Tests for wiki page create, edit, and delete views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.models import UNTAGGED_SENTINEL, WikiPage, WikiPageTag


@tag("views")
class WikiPageCreateViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiPageCreateView."""

    def test_create_view_returns_200(self):
        """Create page view returns 200 for maintainers."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-page-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Doc")

    def test_create_view_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(reverse("wiki-page-create"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_create_view_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("wiki-page-create"))

        self.assertEqual(response.status_code, 403)

    def test_create_page_with_title_and_content(self):
        """Creating a page with title and content works."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            reverse("wiki-page-create"),
            {
                "title": "New Page",
                "content": "Page content here",
            },
        )

        self.assertEqual(response.status_code, 302)
        page = WikiPage.objects.get(slug="new-page")
        self.assertEqual(page.title, "New Page")
        self.assertEqual(page.content, "Page content here")
        self.assertEqual(page.created_by, self.maintainer_user)
        self.assertEqual(page.updated_by, self.maintainer_user)

    def test_create_page_auto_generates_slug(self):
        """Slug is auto-generated from title if not provided."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            reverse("wiki-page-create"),
            {
                "title": "My Great Title",
                "content": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        page = WikiPage.objects.get(slug="my-great-title")
        self.assertEqual(page.title, "My Great Title")

    def test_create_page_with_tags(self):
        """Creating a page with tags creates WikiPageTag records."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            reverse("wiki-page-create"),
            {
                "title": "Tagged Page",
                "content": "",
                "tags": ["machines/blackout", "guides"],
            },
        )

        self.assertEqual(response.status_code, 302)
        page = WikiPage.objects.get(slug="tagged-page")
        tags = set(page.tags.values_list("tag", flat=True))
        self.assertEqual(tags, {"machines/blackout", "guides"})

    def test_create_page_untagged_gets_sentinel(self):
        """Creating a page without tags creates the empty tag sentinel."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            reverse("wiki-page-create"),
            {
                "title": "Untagged",
                "content": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        page = WikiPage.objects.get(slug="untagged")
        self.assertTrue(page.tags.filter(tag=UNTAGGED_SENTINEL).exists())


@tag("views")
class WikiPageEditViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiPageEditView."""

    def test_edit_view_returns_200(self):
        """Edit page view returns 200."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-edit", args=["test"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit: Test")

    def test_edit_view_tagged_page(self):
        """Edit view works for tagged pages."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="docs", slug="test")

        response = self.client.get(reverse("wiki-page-edit", args=["docs/test"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit: Test")

    def test_edit_view_requires_login(self):
        """Unauthenticated users are redirected to login."""
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-edit", args=["test"]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_edit_view_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-edit", args=["test"]))

        self.assertEqual(response.status_code, 403)

    def test_edit_view_missing_page_returns_404(self):
        """Editing non-existent page returns 404."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-page-edit", args=["nonexistent"]))

        self.assertEqual(response.status_code, 404)

    def test_edit_page_updates_content(self):
        """Editing a page updates its content."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Original", slug="test", content="Old")

        response = self.client.post(
            reverse("wiki-page-edit", args=["test"]),
            {
                "title": "Updated",
                "content": "New content",
            },
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertEqual(page.title, "Updated")
        self.assertEqual(page.content, "New content")
        self.assertEqual(page.updated_by, self.maintainer_user)

    def test_edit_page_adds_tags(self):
        """Editing a page can add new tags."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.post(
            reverse("wiki-page-edit", args=["test"]),
            {
                "title": "Test",
                "content": "",
                "tags": ["machines", "guides"],
            },
        )

        self.assertEqual(response.status_code, 302)
        page = WikiPage.objects.get(slug="test")
        tags = set(page.tags.values_list("tag", flat=True))
        self.assertEqual(tags, {"machines", "guides"})

    def test_edit_page_removes_tags(self):
        """Editing a page can remove existing tags."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="machines", slug="test")
        WikiPageTag.objects.create(page=page, tag="guides", slug="test")

        response = self.client.post(
            reverse("wiki-page-edit", args=["machines/test"]),
            {
                "title": "Test",
                "content": "",
                "tags": ["machines"],  # Remove 'guides'
            },
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        tags = set(page.tags.values_list("tag", flat=True))
        self.assertEqual(tags, {"machines"})

    def test_edit_page_prepopulates_tags(self):
        """Edit form prepopulates existing tags."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="machines", slug="test")
        WikiPageTag.objects.create(page=page, tag="guides", slug="test")

        response = self.client.get(reverse("wiki-page-edit", args=["machines/test"]))

        self.assertEqual(response.status_code, 200)
        # Check that tags are prepopulated in the form
        self.assertContains(response, "machines")
        self.assertContains(response, "guides")

    def test_edit_title_updates_slug(self):
        """Renaming a page's title auto-updates the slug."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Old Title", slug="old-title")

        response = self.client.post(
            reverse("wiki-page-edit", args=["old-title"]),
            {"title": "New Title", "content": ""},
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertEqual(page.slug, "new-title")

    def test_edit_title_updates_slug_on_tagged_page(self):
        """Renaming a tagged page updates slug in all tags."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Old Title", slug="old-title")
        WikiPageTag.objects.create(page=page, tag="machines", slug="old-title")

        response = self.client.post(
            reverse("wiki-page-edit", args=["machines/old-title"]),
            {"title": "New Title", "content": "", "tags": ["machines"]},
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertEqual(page.slug, "new-title")
        # All WikiPageTag slugs should be updated too
        tag_slugs = list(page.tags.values_list("slug", flat=True))
        self.assertTrue(all(s == "new-title" for s in tag_slugs))

    def test_rename_to_colliding_slug_shows_form_error(self):
        """Renaming to a title that collides with another page shows a form error."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Maintenance", slug="maintenance")
        WikiPage.objects.create(title="Moopah", slug="moopah")

        response = self.client.post(
            reverse("wiki-page-edit", args=["moopah"]),
            {"title": "Maintenance", "content": ""},
        )

        # Should re-render the form with errors, not crash
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")


@tag("views")
class WikiPageDeleteViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiPageDeleteView."""

    def test_delete_view_returns_200(self):
        """Delete confirmation page returns 200."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-delete", args=["test"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Doc")
        self.assertContains(response, "Test")

    def test_delete_view_requires_login(self):
        """Unauthenticated users are redirected to login."""
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-delete", args=["test"]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_delete_view_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.get(reverse("wiki-page-delete", args=["test"]))

        self.assertEqual(response.status_code, 403)

    def test_delete_view_missing_page_returns_404(self):
        """Deleting non-existent page returns 404."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-page-delete", args=["nonexistent"]))

        self.assertEqual(response.status_code, 404)

    def test_delete_page_post_deletes_page(self):
        """POST to delete view deletes the page."""
        self.client.force_login(self.maintainer_user)
        WikiPage.objects.create(title="Test", slug="test")

        response = self.client.post(reverse("wiki-page-delete", args=["test"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("wiki-home"))
        self.assertFalse(WikiPage.objects.filter(slug="test").exists())

    def test_delete_page_cascades_to_tags(self):
        """Deleting a page also deletes its WikiPageTag records."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="machines", slug="test")

        self.client.post(reverse("wiki-page-delete", args=["machines/test"]))

        self.assertFalse(WikiPage.objects.filter(slug="test").exists())
        self.assertFalse(WikiPageTag.objects.filter(slug="test").exists())


@tag("views")
class WikiTagAutocompleteViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for WikiTagAutocompleteView."""

    def test_returns_json_with_tags(self):
        """API returns JSON with list of distinct tags."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="machines", slug="test")
        WikiPageTag.objects.create(page=page, tag="guides", slug="test")

        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIn("tags", data)
        self.assertEqual(set(data["tags"]), {"machines", "guides"})

    def test_excludes_empty_tag_sentinel(self):
        """API excludes the empty string tag sentinel."""
        self.client.force_login(self.maintainer_user)
        # Create untagged page (sentinel is created automatically via post_save signal)
        page1 = WikiPage.objects.create(title="Untagged Page", slug="untagged-page")
        # Verify sentinel was created
        self.assertTrue(page1.tags.filter(tag=UNTAGGED_SENTINEL).exists())
        # Create tagged page
        page2 = WikiPage.objects.create(title="Tagged Page", slug="tagged-page")
        WikiPageTag.objects.create(page=page2, tag="machines", slug="tagged-page")

        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        data = response.json()
        self.assertEqual(data["tags"], ["machines"])
        self.assertNotIn("", data["tags"])

    def test_returns_distinct_tags(self):
        """API returns each tag only once even if used by multiple pages."""
        self.client.force_login(self.maintainer_user)
        page1 = WikiPage.objects.create(title="Page 1", slug="page-1")
        page2 = WikiPage.objects.create(title="Page 2", slug="page-2")
        WikiPageTag.objects.create(page=page1, tag="machines", slug="page-1")
        WikiPageTag.objects.create(page=page2, tag="machines", slug="page-2")

        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        data = response.json()
        self.assertEqual(data["tags"], ["machines"])

    def test_returns_sorted_tags(self):
        """API returns tags in alphabetical order."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Test", slug="test")
        WikiPageTag.objects.create(page=page, tag="zebra", slug="test")
        WikiPageTag.objects.create(page=page, tag="alpha", slug="test")
        WikiPageTag.objects.create(page=page, tag="machines/beta", slug="test")

        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        data = response.json()
        self.assertEqual(data["tags"], ["alpha", "machines/beta", "zebra"])

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("api-wiki-tag-autocomplete"))

        self.assertEqual(response.status_code, 403)
