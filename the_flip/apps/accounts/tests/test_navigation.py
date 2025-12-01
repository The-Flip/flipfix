"""Tests for navigation display based on auth state."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import create_user


@tag("views", "ui")
class NavigationTests(TestCase):
    """Tests for navigation display based on auth state."""

    def test_nav_shows_login_when_not_authenticated(self):
        """Navigation should show login link when not authenticated."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="/login/"')
        # When not authenticated, no avatar/dropdown should be present
        self.assertNotContains(response, 'class="avatar"')

    def test_nav_shows_user_menu_when_authenticated(self):
        """Navigation should show user menu when authenticated."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        # User dropdown should be present with avatar and profile link
        self.assertContains(response, 'class="avatar"')
        self.assertContains(response, 'href="/profile/"')

    def test_nav_shows_initials_with_full_name(self):
        """Avatar should show both initials when first and last name are set."""
        user = create_user(username="testuser", first_name="John", last_name="Doe")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "JD")

    def test_nav_shows_first_initial_with_first_name_only(self):
        """Avatar should show first initial when only first name is set."""
        user = create_user(username="testuser", first_name="John")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('class="avatar"', content)
        # Should contain J but not JD
        self.assertIn(">J<", content.replace("\n", "").replace(" ", ""))

    def test_nav_shows_username_initial_with_no_name(self):
        """Avatar should show username initial when no name is set."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('class="avatar"', content)
        # Should contain T (first letter of testuser, uppercase)
        self.assertIn(">T<", content.replace("\n", "").replace(" ", ""))
