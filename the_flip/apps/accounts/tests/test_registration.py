"""Tests for account registration views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Invitation, Maintainer
from the_flip.apps.core.test_utils import create_staff_user, create_superuser, create_user

User = get_user_model()


@tag("views", "registration")
class InvitationRegistrationViewTests(TestCase):
    """Tests for the invitation registration view."""

    def setUp(self):
        """Set up test data."""
        self.invitation = Invitation.objects.create(email="newuser@example.com")
        self.register_url = reverse("invitation-register", kwargs={"token": self.invitation.token})

    def test_registration_page_loads(self):
        """Registration page should load with valid token."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/invitation_register.html")
        self.assertContains(response, "Complete Your Registration")

    def test_registration_form_prefills_email(self):
        """Email field should be pre-filled with invitation email."""
        response = self.client.get(self.register_url)
        self.assertContains(response, 'value="newuser@example.com"')

    def test_registration_with_invalid_token_returns_404(self):
        """Invalid token should return 404."""
        url = reverse("invitation-register", kwargs={"token": "invalid-token"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_used_invitation_redirects_with_error(self):
        """Used invitation should redirect to login with error message."""
        self.invitation.used = True
        self.invitation.save()

        response = self.client.get(self.register_url, follow=True)
        self.assertRedirects(response, reverse("login"))
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("already been used", str(messages[0]))

    def test_successful_registration(self):
        """Successful registration creates user, maintainer, and marks invitation used."""
        data = {
            "username": "newmaintainer",
            "first_name": "New",
            "last_name": "Maintainer",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, follow=True)

        # Should redirect to home
        self.assertRedirects(response, reverse("home"))

        # User should be created
        user = User.objects.get(username="newmaintainer")
        self.assertEqual(user.email, "newuser@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Maintainer")
        self.assertTrue(user.is_staff)

        # Maintainer should be created
        self.assertTrue(Maintainer.objects.filter(user=user).exists())

        # Invitation should be marked as used
        self.invitation.refresh_from_db()
        self.assertTrue(self.invitation.used)

        # User should be logged in
        self.assertTrue(response.context["user"].is_authenticated)

    def test_registration_allows_different_email(self):
        """User can register with a different email than the invitation."""
        data = {
            "username": "newmaintainer",
            "email": "different@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        self.client.post(self.register_url, data, follow=True)

        user = User.objects.get(username="newmaintainer")
        self.assertEqual(user.email, "different@example.com")

    def test_registration_validates_password_match(self):
        """Registration should fail if passwords don't match."""
        data = {
            "username": "newmaintainer",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "DifferentPass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match")
        self.assertFalse(User.objects.filter(username="newmaintainer").exists())

    def test_registration_validates_username_uniqueness(self):
        """Registration should fail if username is taken."""
        create_user(username="existinguser")

        data = {
            "username": "existinguser",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username is already taken")

    def test_registration_validates_email_uniqueness(self):
        """Registration should fail if email is already registered."""
        create_user(username="existing", email="newuser@example.com")

        data = {
            "username": "newmaintainer",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "email is already registered")

    def test_registration_validates_password_strength(self):
        """Registration should enforce password validation rules."""
        data = {
            "username": "newmaintainer",
            "email": "newuser@example.com",
            "password": "123",  # Too short and common
            "password_confirm": "123",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        # Django's password validators will catch this
        self.assertFalse(User.objects.filter(username="newmaintainer").exists())


@tag("views", "registration")
class SelfRegistrationViewTests(TestCase):
    """Tests for the self-registration view (beta feature)."""

    def setUp(self):
        """Set up test data."""
        self.register_url = reverse("self-register")
        self.check_username_url = reverse("check-username")

        # Create an unclaimed user (has @example.com email, not admin)
        self.unclaimed_user = create_staff_user(
            username="unclaimed",
            email="unclaimed@example.com",
            first_name="Old",
            last_name="Name",
        )
        Maintainer.objects.get_or_create(user=self.unclaimed_user)

        # Create an admin user (cannot be claimed)
        self.admin_user = create_superuser(username="admin")

        # Create a claimed user (has real email, not @example.com)
        self.claimed_user = create_staff_user(
            username="claimed",
            email="claimed@realemail.com",
        )
        Maintainer.objects.get_or_create(user=self.claimed_user)

    def test_registration_page_loads(self):
        """Registration page should load."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/self_register.html")
        self.assertContains(response, "Register")

    def test_claim_existing_unclaimed_account(self):
        """Should be able to claim an unclaimed account."""
        data = {
            "username": "unclaimed",
            "first_name": "New",
            "last_name": "Name",
            "email": "real@email.com",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, follow=True)

        self.assertRedirects(response, reverse("home"))

        # User should be updated
        self.unclaimed_user.refresh_from_db()
        self.assertEqual(self.unclaimed_user.email, "real@email.com")
        self.assertEqual(self.unclaimed_user.first_name, "New")
        self.assertEqual(self.unclaimed_user.last_name, "Name")
        self.assertTrue(self.unclaimed_user.check_password("SecurePass123!"))

        # User should be logged in
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertEqual(response.context["user"].username, "unclaimed")

        # Should show welcome message
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Welcome to The Flip", str(messages[0]))

    def test_claim_without_email_clears_example_email(self):
        """Claiming without email should clear the @example.com email."""
        data = {
            "username": "unclaimed",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, follow=True)

        self.assertRedirects(response, reverse("home"))
        self.unclaimed_user.refresh_from_db()
        self.assertEqual(self.unclaimed_user.email, "")

    def test_claim_preserves_existing_names_if_not_provided(self):
        """Claiming should preserve existing first/last name if not provided."""
        data = {
            "username": "unclaimed",
            "password": "SecurePass123!",
        }
        self.client.post(self.register_url, data, follow=True)

        self.unclaimed_user.refresh_from_db()
        self.assertEqual(self.unclaimed_user.first_name, "Old")
        self.assertEqual(self.unclaimed_user.last_name, "Name")

    def test_create_new_account(self):
        """Should be able to create a new account."""
        data = {
            "username": "brandnew",
            "first_name": "Brand",
            "last_name": "New",
            "email": "brandnew@email.com",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, follow=True)

        self.assertRedirects(response, reverse("home"))

        # User should be created
        user = User.objects.get(username="brandnew")
        self.assertEqual(user.email, "brandnew@email.com")
        self.assertEqual(user.first_name, "Brand")
        self.assertEqual(user.last_name, "New")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("SecurePass123!"))

        # Maintainer should be created
        self.assertTrue(Maintainer.objects.filter(user=user).exists())

        # User should be logged in
        self.assertTrue(response.context["user"].is_authenticated)

    def test_cannot_claim_admin_account(self):
        """Should not be able to claim an admin account."""
        data = {
            "username": "admin",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not available")

    def test_cannot_claim_already_claimed_account(self):
        """Should not be able to claim an already-claimed account."""
        data = {
            "username": "claimed",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")

    def test_password_validation(self):
        """Registration should enforce password validation rules."""
        data = {
            "username": "newuser",
            "password": "123",  # Too short
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_email_uniqueness(self):
        """Registration should reject email already used by another user."""
        data = {
            "username": "newuser",
            "email": "claimed@realemail.com",  # Already used
            "password": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered")


@tag("api", "ajax")
class CheckUsernameViewTests(TestCase):
    """Tests for the check-username AJAX endpoint."""

    def setUp(self):
        """Set up test data."""
        self.check_url = reverse("check-username")

        # Unclaimed user
        create_staff_user(username="unclaimed", email="unclaimed@example.com")

        # Admin user
        create_superuser(username="admin")

        # Claimed user
        create_staff_user(username="claimed", email="claimed@realemail.com")

    def test_unclaimed_username_is_available(self):
        """Unclaimed usernames should be available."""
        response = self.client.get(self.check_url + "?q=unclaimed")
        data = response.json()

        self.assertTrue(data["available"])
        self.assertTrue(data["exists"])

    def test_new_username_is_available(self):
        """New usernames should be available."""
        response = self.client.get(self.check_url + "?q=brandnew")
        data = response.json()

        self.assertTrue(data["available"])
        self.assertFalse(data["exists"])

    def test_admin_username_not_available(self):
        """Admin usernames should not be available."""
        response = self.client.get(self.check_url + "?q=admin")
        data = response.json()

        self.assertFalse(data["available"])
        self.assertTrue(data["exists"])

    def test_claimed_username_not_available(self):
        """Already-claimed usernames should not be available."""
        response = self.client.get(self.check_url + "?q=claimed")
        data = response.json()

        self.assertFalse(data["available"])
        self.assertTrue(data["exists"])

    def test_suggestions_only_include_claimable_users(self):
        """Suggestions should only include claimable (unclaimed, non-admin) users."""
        response = self.client.get(self.check_url + "?q=un")
        data = response.json()

        self.assertIn("unclaimed", data["suggestions"])
        self.assertNotIn("admin", data["suggestions"])
        self.assertNotIn("claimed", data["suggestions"])

    def test_minimum_query_length(self):
        """Should require minimum 2 characters for suggestions."""
        response = self.client.get(self.check_url + "?q=u")
        data = response.json()

        self.assertFalse(data["available"])
        self.assertEqual(data["suggestions"], [])

    def test_case_insensitive_check(self):
        """Username check should be case-insensitive."""
        response = self.client.get(self.check_url + "?q=UNCLAIMED")
        data = response.json()

        self.assertTrue(data["available"])
        self.assertTrue(data["exists"])
