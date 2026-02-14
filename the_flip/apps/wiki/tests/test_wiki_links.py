"""Tests for wiki page link rendering in markdown."""

from django.test import TestCase, tag

from the_flip.apps.core.templatetags.markdown_tags import render_markdown
from the_flip.apps.wiki.models import WikiPage, WikiPageTag


@tag("views")
class WikiPageLinkRenderingTests(TestCase):
    """Tests for [[page:id:N]] wiki link rendering."""

    def test_wiki_link_renders_as_anchor(self):
        """[[page:id:N]] renders as a link with page title."""
        page = WikiPage.objects.create(title="Test Page", slug="test-page")
        page_tag = WikiPageTag.objects.create(page=page, tag="docs", slug="test-page")

        result = render_markdown(f"See [[page:id:{page_tag.pk}]] for details.")

        self.assertIn("<a href=", result)
        self.assertIn("Test Page", result)
        self.assertIn("/doc/docs/test-page", result)

    def test_wiki_link_untagged_page(self):
        """[[page:id:N]] for untagged page uses root path."""
        # Signal auto-creates untagged sentinel
        page = WikiPage.objects.create(title="Root Page", slug="root-page")
        page_tag = page.tags.first()  # Get the auto-created sentinel

        result = render_markdown(f"See [[page:id:{page_tag.pk}]].")

        self.assertIn("/doc/root-page", result)
        self.assertIn("Root Page", result)

    def test_wiki_link_deleted_page(self):
        """[[page:id:N]] for deleted WikiPageTag shows [broken link] text."""
        result = render_markdown("See [[page:id:99999]] for info.")

        self.assertIn("[broken link]", result)
        self.assertIn("<em>", result)  # *[broken link]* renders as italic

    def test_multiple_wiki_links(self):
        """Multiple [[page:id:N]] links in same text all render."""
        # Signal auto-creates untagged sentinels
        page1 = WikiPage.objects.create(title="First", slug="first")
        page2 = WikiPage.objects.create(title="Second", slug="second")
        tag1 = page1.tags.first()
        tag2 = page2.tags.first()

        result = render_markdown(f"See [[page:id:{tag1.pk}]] and [[page:id:{tag2.pk}]].")

        self.assertIn("First", result)
        self.assertIn("Second", result)
        self.assertIn("/doc/first", result)
        self.assertIn("/doc/second", result)

    def test_wiki_link_with_nested_tag(self):
        """[[page:id:N]] renders correct path for nested tags."""
        page = WikiPage.objects.create(title="Nested Page", slug="nested")
        page_tag = WikiPageTag.objects.create(page=page, tag="machines/blackout", slug="nested")

        result = render_markdown(f"See [[page:id:{page_tag.pk}]].")

        self.assertIn("/doc/machines/blackout/nested", result)

    def test_no_wiki_links_unchanged(self):
        """Text without wiki links renders normally."""
        result = render_markdown("Just regular **markdown** text.")

        self.assertIn("<strong>markdown</strong>", result)
        self.assertNotIn("[[", result)

    def test_wiki_link_escapes_title(self):
        """Page titles with special chars are escaped in output."""
        # Signal auto-creates untagged sentinel
        page = WikiPage.objects.create(title="Test <script>", slug="test")
        page_tag = page.tags.first()

        result = render_markdown(f"See [[page:id:{page_tag.pk}]].")

        # Title should be escaped, not raw HTML
        self.assertNotIn("<script>", result)
