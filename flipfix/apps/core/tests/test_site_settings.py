"""Tests for the SiteSettings singleton model, form, and views."""

from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.core.forms import SiteSettingsForm
from flipfix.apps.core.models import SiteSettings
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_maintainer_user,
    create_superuser,
)

# =============================================================================
# Model tests
# =============================================================================


@tag("models")
class SiteSettingsModelTests(TestCase):
    """Tests for the SiteSettings singleton model."""

    def test_load_creates_row_when_none_exists(self):
        """load() should create the singleton row if the table is empty."""
        SiteSettings.objects.all().delete()
        settings = SiteSettings.load()
        self.assertEqual(settings.pk, 1)
        self.assertEqual(settings.front_page_content, "")

    def test_load_returns_existing_row(self):
        """load() should return the existing row without duplicating."""
        SiteSettings.objects.all().delete()
        SiteSettings.objects.create(pk=1, front_page_content="hello")
        settings = SiteSettings.load()
        self.assertEqual(settings.front_page_content, "hello")
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_save_forces_pk_1(self):
        """save() should always force pk=1, preventing duplicate rows."""
        obj = SiteSettings(front_page_content="test")
        obj.pk = 999
        obj.save()
        self.assertEqual(obj.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_delete_is_noop(self):
        """delete() should not remove the singleton row."""
        settings = SiteSettings.load()
        settings.delete()
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_str(self):
        """__str__ should return 'Site Settings'."""
        self.assertEqual(str(SiteSettings.load()), "Site Settings")


# =============================================================================
# Form tests
# =============================================================================


@tag("forms")
class SiteSettingsFormTests(TestCase):
    """Tests for SiteSettingsForm."""

    def test_empty_content_is_valid(self):
        """Submitting empty content should be valid (front page shows nothing)."""
        settings = SiteSettings.load()
        form = SiteSettingsForm(data={"front_page_content": ""}, instance=settings)
        self.assertTrue(form.is_valid())

    def test_content_is_saved(self):
        """Content should be saved to the model."""
        settings = SiteSettings.load()
        form = SiteSettingsForm(data={"front_page_content": "# Hello"}, instance=settings)
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertEqual(saved.front_page_content, "# Hello")

    def test_plain_text_passes_through_unchanged(self):
        """Content without [[links]] should pass through the clean method unchanged."""
        settings = SiteSettings.load()
        form = SiteSettingsForm(
            data={"front_page_content": "Some **bold** text"}, instance=settings
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["front_page_content"], "Some **bold** text")


# =============================================================================
# View access control tests
# =============================================================================


@tag("views")
class SiteSettingsAccessTests(AccessControlTestCase):
    """Tests for SiteSettingsEditView access control."""

    def setUp(self):
        super().setUp()
        self.url = reverse("site-settings")
        self.maintainer_user = create_maintainer_user()
        self.superuser = create_superuser()

    def test_anonymous_redirects_to_login(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_maintainer_gets_403(self):
        """Regular maintainers should get 403."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_gets_200(self):
        """Superusers should be able to access the edit form."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/site_settings_form.html")


# =============================================================================
# View functional tests
# =============================================================================


@tag("views")
class SiteSettingsEditViewTests(TestCase):
    """Tests for SiteSettingsEditView functionality."""

    def setUp(self):
        self.superuser = create_superuser()
        self.client.force_login(self.superuser)
        self.url = reverse("site-settings")

    def test_get_loads_existing_content(self):
        """GET should display the current front_page_content."""
        settings = SiteSettings.load()
        settings.front_page_content = "# Current content"
        settings.save()

        response = self.client.get(self.url)
        self.assertContains(response, "Current content")

    def test_post_saves_content(self):
        """POST should save the new content."""
        response = self.client.post(self.url, {"front_page_content": "# New content"})
        self.assertRedirects(response, self.url)

        settings = SiteSettings.load()
        self.assertEqual(settings.front_page_content, "# New content")

    def test_post_empty_content_allowed(self):
        """POST with empty content should be accepted (clears front page)."""
        response = self.client.post(self.url, {"front_page_content": ""})
        self.assertRedirects(response, self.url)

        settings = SiteSettings.load()
        self.assertEqual(settings.front_page_content, "")

    def test_success_message_on_save(self):
        """Saving should show a success toast message."""
        response = self.client.post(self.url, {"front_page_content": "# Updated"}, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Site settings saved.")


# =============================================================================
# Home page rendering tests
# =============================================================================


@tag("views")
class HomePageRenderingTests(TestCase):
    """Tests for front page content rendering on the public home page."""

    def test_renders_markdown_content(self):
        """Home page should render the markdown content from SiteSettings."""
        settings = SiteSettings.load()
        settings.front_page_content = "## Welcome to the museum"
        settings.save()

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Welcome to the museum")
        self.assertContains(response, "<h2>")

    def test_empty_content_shows_nothing(self):
        """Home page should show nothing when front_page_content is empty."""
        settings = SiteSettings.load()
        settings.front_page_content = ""
        settings.save()

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "markdown-content")
