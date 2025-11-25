"""Tests for accounts app."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Invitation, Maintainer

User = get_user_model()


class MaintainerModelTests(TestCase):
    """Tests for the Maintainer model."""

    def test_is_shared_account_defaults_to_false(self):
        """New maintainers should not be shared accounts by default."""
        user = User.objects.create_user(username="testuser", password="testpass123", is_staff=True)
        maintainer = Maintainer.objects.get(user=user)
        self.assertFalse(maintainer.is_shared_account)

    def test_can_create_shared_account(self):
        """Can create a maintainer with is_shared_account=True."""
        user = User.objects.create_user(
            username="workshop-terminal", password="testpass123", is_staff=True
        )
        maintainer = Maintainer.objects.get(user=user)
        maintainer.is_shared_account = True
        maintainer.save()

        maintainer.refresh_from_db()
        self.assertTrue(maintainer.is_shared_account)


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


class ProfileViewTests(TestCase):
    """Tests for the profile view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
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
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile.html")

    def test_profile_displays_current_data(self):
        """Profile form should show current user data."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.profile_url)
        self.assertContains(response, 'value="test@example.com"')
        self.assertContains(response, 'value="Test"')
        self.assertContains(response, 'value="User"')

    def test_profile_update_saves_changes(self):
        """Profile update should save changes."""
        self.client.login(username="testuser", password="testpass123")
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
        self.client.login(username="testuser", password="testpass123")
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
        User.objects.create_user(
            username="otheruser", email="taken@example.com", password="pass123"
        )
        self.client.login(username="testuser", password="testpass123")
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
        self.client.login(username="testuser", password="testpass123")
        data = {
            "email": "test@example.com",
            "first_name": "Updated",
            "last_name": "User",
        }
        response = self.client.post(self.profile_url, data, follow=True)
        self.assertRedirects(response, self.profile_url)


class PasswordChangeViewTests(TestCase):
    """Tests for the password change view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="oldpass123"
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
        self.client.login(username="testuser", password="oldpass123")
        response = self.client.get(self.password_change_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_change_form.html")

    def test_password_change_success(self):
        """Password change should work with valid data."""
        self.client.login(username="testuser", password="oldpass123")
        data = {
            "old_password": "oldpass123",
            "new_password1": "NewSecurePass456!",
            "new_password2": "NewSecurePass456!",
        }
        response = self.client.post(self.password_change_url, data, follow=True)
        self.assertRedirects(response, self.password_change_done_url)

        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecurePass456!"))

    def test_password_change_done_page(self):
        """Password change done page should display success message."""
        self.client.login(username="testuser", password="oldpass123")
        response = self.client.get(self.password_change_done_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password Changed")


class NavigationTests(TestCase):
    """Tests for navigation display based on auth state."""

    def test_nav_shows_login_when_not_authenticated(self):
        """Navigation should show login link when not authenticated."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="/login/"')
        self.assertNotContains(response, "user-menu")

    def test_nav_shows_user_menu_when_authenticated(self):
        """Navigation should show user menu when authenticated."""
        User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "user-menu")
        self.assertContains(response, 'href="/profile/"')

    def test_nav_shows_initials_with_full_name(self):
        """Avatar should show both initials when first and last name are set."""
        User.objects.create_user(
            username="testuser",
            password="testpass123",
            first_name="John",
            last_name="Doe",
        )
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "JD")

    def test_nav_shows_first_initial_with_first_name_only(self):
        """Avatar should show first initial when only first name is set."""
        User.objects.create_user(username="testuser", password="testpass123", first_name="John")
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("user-menu__avatar", content)
        # Should contain J but not JD
        self.assertIn(">J<", content.replace("\n", "").replace(" ", ""))

    def test_nav_shows_username_initial_with_no_name(self):
        """Avatar should show username initial when no name is set."""
        User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("user-menu__avatar", content)
        # Should contain t (first letter of testuser)
        self.assertIn(">t<", content.replace("\n", "").replace(" ", ""))
