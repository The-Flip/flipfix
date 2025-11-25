"""Tests for accounts app."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Invitation, Maintainer

User = get_user_model()


class InvitationModelTests(TestCase):
    """Tests for the Invitation model."""

    def test_invitation_generates_unique_token(self):
        """Each invitation should have a unique token."""
        inv1 = Invitation.objects.create(email="user1@example.com")
        inv2 = Invitation.objects.create(email="user2@example.com")
        self.assertNotEqual(inv1.token, inv2.token)
        self.assertTrue(len(inv1.token) > 20)

    def test_invitation_str_pending(self):
        """String representation shows pending status."""
        inv = Invitation.objects.create(email="test@example.com")
        self.assertEqual(str(inv), "test@example.com (pending)")

    def test_invitation_str_used(self):
        """String representation shows used status."""
        inv = Invitation.objects.create(email="test@example.com", used=True)
        self.assertEqual(str(inv), "test@example.com (used)")

    def test_email_must_be_unique(self):
        """Cannot create two invitations with the same email."""
        Invitation.objects.create(email="test@example.com")
        with self.assertRaises(IntegrityError):
            Invitation.objects.create(email="test@example.com")


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
        User.objects.create_user(username="existinguser", password="test123")

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
        User.objects.create_user(
            username="existing", email="newuser@example.com", password="test123"
        )

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


class InvitationAdminTests(TestCase):
    """Tests for the Invitation admin interface."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staffuser", password="staffpass123", is_staff=True
        )
        self.admin_url = "/admin/accounts/invitation/"

    def test_superuser_can_access_invitation_admin(self):
        """Superusers should be able to access the invitation admin."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.admin_url)
        self.assertEqual(response.status_code, 200)

    def test_staff_user_cannot_access_invitation_admin(self):
        """Non-superuser staff should not see the invitation admin."""
        self.client.login(username="staffuser", password="staffpass123")
        response = self.client.get(self.admin_url)
        # Should get 403 since they don't have permission
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_create_invitation(self):
        """Superusers should be able to create invitations."""
        self.client.login(username="admin", password="adminpass123")
        add_url = "/admin/accounts/invitation/add/"
        response = self.client.post(add_url, {"email": "invite@example.com"})
        self.assertEqual(response.status_code, 302)  # Redirect after success
        self.assertTrue(Invitation.objects.filter(email="invite@example.com").exists())
