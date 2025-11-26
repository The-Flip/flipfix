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


class SelfRegistrationViewTests(TestCase):
    """Tests for the self-registration view (beta feature)."""

    def setUp(self):
        """Set up test data."""
        self.register_url = reverse("self-register")
        self.check_username_url = reverse("check-username")

        # Create an unclaimed user (has @example.com email, not admin)
        self.unclaimed_user = User.objects.create_user(
            username="unclaimed",
            email="unclaimed@example.com",
            password="test123",
            first_name="Old",
            last_name="Name",
            is_staff=True,
        )
        Maintainer.objects.get_or_create(user=self.unclaimed_user)

        # Create an admin user (cannot be claimed)
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",
        )

        # Create a claimed user (has real email, not @example.com)
        self.claimed_user = User.objects.create_user(
            username="claimed",
            email="claimed@realemail.com",
            password="SecurePass123!",
            is_staff=True,
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


class CheckUsernameViewTests(TestCase):
    """Tests for the check-username AJAX endpoint."""

    def setUp(self):
        """Set up test data."""
        self.check_url = reverse("check-username")

        # Unclaimed user
        User.objects.create_user(
            username="unclaimed",
            email="unclaimed@example.com",
            password="test123",
            is_staff=True,
        )

        # Admin user
        User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",
        )

        # Claimed user
        User.objects.create_user(
            username="claimed",
            email="claimed@realemail.com",
            password="pass123",
            is_staff=True,
        )

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


class TerminalListViewTests(TestCase):
    """Tests for the terminal list view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staffuser", password="staffpass123", is_staff=True
        )
        self.list_url = reverse("terminal-list")

        # Create a shared terminal
        terminal_user = User.objects.create_user(
            username="workshop-terminal",
            password="randompass",
            first_name="Workshop",
            last_name="Terminal",
            is_staff=True,
        )
        self.terminal = Maintainer.objects.get(user=terminal_user)
        self.terminal.is_shared_account = True
        self.terminal.save()

    def test_requires_superuser(self):
        """Terminal list should require superuser access."""
        # Not logged in
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)

        # Staff user (not superuser)
        self.client.login(username="staffuser", password="staffpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal list."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_list.html")

    def test_lists_shared_terminals(self):
        """Terminal list should show shared terminal accounts."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "Workshop Terminal")

    def test_shows_deactivated_label(self):
        """Deactivated terminals should show (deactivated) label."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "(deactivated)")

    def test_empty_state(self):
        """Should show message when no terminals exist."""
        self.terminal.delete()

        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "No shared terminal accounts have been created yet")


class TerminalLoginViewTests(TestCase):
    """Tests for the terminal login view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )

        terminal_user = User.objects.create_user(
            username="workshop-terminal",
            password="randompass",
            first_name="Workshop",
            last_name="Terminal",
            is_staff=True,
        )
        self.terminal = Maintainer.objects.get(user=terminal_user)
        self.terminal.is_shared_account = True
        self.terminal.save()

        self.login_url = reverse("terminal-login", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal login should require POST request."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 405)

    def test_superuser_can_login_as_terminal(self):
        """Superuser should be able to log in as terminal."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.login_url, follow=True)

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(response.context["user"].username, "workshop-terminal")

    def test_shows_success_message(self):
        """Login should show success message."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.login_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Logged in as", str(messages[0]))

    def test_cannot_login_to_deactivated_terminal(self):
        """Should not be able to log in to deactivated terminal."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.login_url)
        self.assertEqual(response.status_code, 404)


class TerminalCreateViewTests(TestCase):
    """Tests for the terminal create view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.add_url = reverse("terminal-add")

    def test_requires_superuser(self):
        """Terminal create should require superuser access."""
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal create page."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_form.html")

    def test_creates_terminal(self):
        """Should create a shared terminal account."""
        self.client.login(username="admin", password="adminpass123")
        data = {
            "username": "new-terminal",
            "first_name": "New",
            "last_name": "Terminal",
        }
        response = self.client.post(self.add_url, data, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        # User should be created
        user = User.objects.get(username="new-terminal")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Terminal")
        self.assertTrue(user.is_staff)

        # Maintainer should be shared
        maintainer = Maintainer.objects.get(user=user)
        self.assertTrue(maintainer.is_shared_account)

    def test_validates_username_uniqueness(self):
        """Should reject duplicate usernames."""
        User.objects.create_user(username="existing", password="test123")

        self.client.login(username="admin", password="adminpass123")
        data = {"username": "existing"}
        response = self.client.post(self.add_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")

    def test_form_has_password_manager_protection(self):
        """Form should have attributes to prevent password manager autofill."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.add_url)

        self.assertContains(response, 'autocomplete="off"')
        self.assertContains(response, "data-1p-ignore")
        self.assertContains(response, 'data-lpignore="true"')


class TerminalUpdateViewTests(TestCase):
    """Tests for the terminal update view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )

        terminal_user = User.objects.create_user(
            username="workshop-terminal",
            password="randompass",
            first_name="Workshop",
            last_name="Terminal",
            is_staff=True,
        )
        self.terminal = Maintainer.objects.get(user=terminal_user)
        self.terminal.is_shared_account = True
        self.terminal.save()

        self.edit_url = reverse("terminal-edit", kwargs={"pk": self.terminal.pk})

    def test_requires_superuser(self):
        """Terminal edit should require superuser access."""
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal edit page."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_form.html")

    def test_prefills_form_data(self):
        """Form should be prefilled with current data."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, 'value="Workshop"')
        self.assertContains(response, 'value="Terminal"')

    def test_shows_username_as_readonly(self):
        """Username should be displayed but not editable."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "workshop-terminal")
        # Should not have an input field for username in edit mode
        self.assertNotContains(response, 'name="username"')

    def test_updates_terminal(self):
        """Should update terminal's first/last name."""
        self.client.login(username="admin", password="adminpass123")
        data = {
            "first_name": "Updated",
            "last_name": "Name",
        }
        response = self.client.post(self.edit_url, data, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertEqual(self.terminal.user.first_name, "Updated")
        self.assertEqual(self.terminal.user.last_name, "Name")

    def test_shows_deactivate_button_for_active_terminal(self):
        """Should show deactivate button for active terminals."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "Deactivate")

    def test_hides_deactivate_button_for_inactive_terminal(self):
        """Should hide deactivate button for inactive terminals."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertNotContains(response, "Deactivate")

    def test_shows_reactivate_button_for_inactive_terminal(self):
        """Should show re-activate button for inactive terminals."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "Re-activate")


class TerminalDeactivateViewTests(TestCase):
    """Tests for the terminal deactivate view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )

        terminal_user = User.objects.create_user(
            username="workshop-terminal",
            password="randompass",
            first_name="Workshop",
            last_name="Terminal",
            is_staff=True,
        )
        self.terminal = Maintainer.objects.get(user=terminal_user)
        self.terminal.is_shared_account = True
        self.terminal.save()

        self.deactivate_url = reverse("terminal-deactivate", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal deactivate should require POST request."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.deactivate_url)
        self.assertEqual(response.status_code, 405)

    def test_deactivates_terminal(self):
        """Should deactivate terminal account."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.deactivate_url, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertFalse(self.terminal.user.is_active)

    def test_shows_success_message(self):
        """Deactivate should show success message."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.deactivate_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("deactivated", str(messages[0]))


class TerminalReactivateViewTests(TestCase):
    """Tests for the terminal reactivate view."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )

        terminal_user = User.objects.create_user(
            username="workshop-terminal",
            password="randompass",
            first_name="Workshop",
            last_name="Terminal",
            is_staff=True,
            is_active=False,
        )
        self.terminal = Maintainer.objects.get(user=terminal_user)
        self.terminal.is_shared_account = True
        self.terminal.save()

        self.reactivate_url = reverse("terminal-reactivate", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal reactivate should require POST request."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.reactivate_url)
        self.assertEqual(response.status_code, 405)

    def test_reactivates_terminal(self):
        """Should reactivate terminal account."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.reactivate_url, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertTrue(self.terminal.user.is_active)

    def test_shows_success_message(self):
        """Reactivate should show success message."""
        self.client.login(username="admin", password="adminpass123")
        response = self.client.post(self.reactivate_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("reactivated", str(messages[0]))


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
