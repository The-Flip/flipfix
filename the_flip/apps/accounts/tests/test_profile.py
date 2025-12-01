"""Tests for user profile views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import create_user

User = get_user_model()


@tag("views")
class ProfileViewTests(TestCase):
    """Tests for the profile view."""

    def setUp(self):
        """Set up test data."""
        self.user = create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )
        self.profile_url = reverse("profile")

    def test_profile_requires_login(self):
        """Profile page should require login."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_profile_loads_for_authenticated_user(self):
        """Profile page should load for authenticated users."""
        self.client.force_login(self.user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile.html")

    def test_profile_displays_current_data(self):
        """Profile form should show current user data."""
        self.client.force_login(self.user)
        response = self.client.get(self.profile_url)
        self.assertContains(response, 'value="test@example.com"')
        self.assertContains(response, 'value="Test"')
        self.assertContains(response, 'value="User"')

    def test_profile_update_saves_changes(self):
        """Profile update should save changes."""
        self.client.force_login(self.user)
        data = {
            "email": "updated@example.com",
            "first_name": "Updated",
            "last_name": "Name",
        }
        response = self.client.post(self.profile_url, data, follow=True)
        self.assertRedirects(response, self.profile_url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Name")

    def test_profile_update_shows_success_message(self):
        """Profile update should show success message."""
        self.client.force_login(self.user)
        data = {
            "email": "updated@example.com",
            "first_name": "Updated",
            "last_name": "Name",
        }
        response = self.client.post(self.profile_url, data, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_profile_email_uniqueness_validation(self):
        """Profile should reject email already used by another user."""
        create_user(username="otheruser", email="taken@example.com")
        self.client.force_login(self.user)
        data = {
            "email": "taken@example.com",
            "first_name": "Test",
            "last_name": "User",
        }
        response = self.client.post(self.profile_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "email is already registered")

    def test_profile_allows_keeping_own_email(self):
        """User should be able to keep their own email."""
        self.client.force_login(self.user)
        data = {
            "email": "test@example.com",
            "first_name": "Updated",
            "last_name": "User",
        }
        response = self.client.post(self.profile_url, data, follow=True)
        self.assertRedirects(response, self.profile_url)


@tag("views", "auth")
class PasswordChangeViewTests(TestCase):
    """Tests for the password change view.

    NOTE: These tests intentionally use login() with explicit passwords rather than
    force_login() because they specifically test password-related functionality.
    """

    # Test password for password change tests (intentionally hardcoded)
    TEST_OLD_PASSWORD = "oldpass123"  # noqa: S105

    def setUp(self):
        """Set up test data."""
        self.user = create_user(
            username="testuser", email="test@example.com", password=self.TEST_OLD_PASSWORD
        )
        self.password_change_url = reverse("password_change")
        self.password_change_done_url = reverse("password_change_done")

    def test_password_change_requires_login(self):
        """Password change page should require login."""
        response = self.client.get(self.password_change_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_password_change_loads_for_authenticated_user(self):
        """Password change page should load for authenticated users."""
        self.client.login(username="testuser", password=self.TEST_OLD_PASSWORD)
        response = self.client.get(self.password_change_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_change_form.html")

    def test_password_change_success(self):
        """Password change should work with valid data."""
        self.client.login(username="testuser", password=self.TEST_OLD_PASSWORD)
        new_password = "NewSecurePass456!"  # noqa: S105
        data = {
            "old_password": self.TEST_OLD_PASSWORD,
            "new_password1": new_password,
            "new_password2": new_password,
        }
        response = self.client.post(self.password_change_url, data, follow=True)
        self.assertRedirects(response, self.password_change_done_url)

        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_password_change_done_page(self):
        """Password change done page should display success message."""
        self.client.login(username="testuser", password=self.TEST_OLD_PASSWORD)
        response = self.client.get(self.password_change_done_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password Changed")
