"""Tests for account registration views."""

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Invitation, Maintainer
from flipfix.apps.core.test_utils import AccessControlTestCase, create_user

User = get_user_model()

# Generate a valid test password that passes Django's validators
# Using secrets module to avoid hardcoded strings that trigger secret scanners
TEST_PASSWORD = f"Test{secrets.token_hex(8)}!"


@tag("views")
class InvitationRegistrationViewTests(AccessControlTestCase):
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
        self.invitation.accepted_at = timezone.now()
        self.invitation.save()

        response = self.client.get(self.register_url, follow=True)
        self.assertRedirects(response, reverse("login"))
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("already been used", str(messages[0]))

    def test_revoked_invitation_says_cancelled_not_used(self):
        """A revoked link must not read as "already used".

        The two mean different things to the reader: one says "you already
        have an account", the other says "ask for a new link".
        """
        self.invitation.revoked_at = timezone.now()
        self.invitation.save()

        response = self.client.get(self.register_url, follow=True)
        self.assertRedirects(response, reverse("login"))
        messages = list(response.context["messages"])
        self.assertIn("cancelled", str(messages[0]))
        self.assertNotIn("already been used", str(messages[0]))

    def test_expired_invitation_says_expired_not_used(self):
        """An expired link tells the reader to ask for another one."""
        self.invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.invitation.save()

        response = self.client.get(self.register_url, follow=True)
        self.assertRedirects(response, reverse("login"))
        messages = list(response.context["messages"])
        self.assertIn("expired", str(messages[0]))
        self.assertNotIn("already been used", str(messages[0]))

    def test_expired_invitation_cannot_be_posted_to(self):
        """Expiry is enforced on POST, not just on the rendered form."""
        self.invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.invitation.save()

        self.client.post(
            self.register_url,
            {
                "username": "toolate",
                "email": "newuser@example.com",
                "password": TEST_PASSWORD,
            },
        )
        self.assertFalse(User.objects.filter(username="toolate").exists())

    def test_successful_registration(self):
        """Successful registration creates user, maintainer, and marks invitation used."""
        data = {
            "username": "newmaintainer",
            "first_name": "New",
            "last_name": "Maintainer",
            "email": "newuser@example.com",
            "password": TEST_PASSWORD,
        }
        response = self.client.post(self.register_url, data, follow=True)

        # Should redirect to home
        self.assertRedirects(response, reverse("home"))

        # User should be created
        user = User.objects.get(username="newmaintainer")
        self.assertEqual(user.email, "newuser@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Maintainer")
        self.assertTrue(user.groups.filter(name="Maintainers").exists())
        self.assertTrue(user.has_perm("accounts.can_access_maintainer_portal"))

        # Maintainer should be created
        self.assertTrue(Maintainer.objects.filter(user=user).exists())

        # Invitation should be claimed, and the chain edge recorded
        self.invitation.refresh_from_db()
        self.assertIsNotNone(self.invitation.accepted_at)
        self.assertEqual(self.invitation.accepted_by, user)
        self.assertEqual(self.invitation.status, Invitation.Status.ACCEPTED)

        # User should be logged in
        self.assertTrue(response.context["user"].is_authenticated)

    def test_registration_allows_different_email(self):
        """User can register with a different email than the invitation."""
        data = {
            "username": "newmaintainer",
            "email": "different@example.com",
            "password": TEST_PASSWORD,
        }
        self.client.post(self.register_url, data, follow=True)

        user = User.objects.get(username="newmaintainer")
        self.assertEqual(user.email, "different@example.com")

    def test_registration_validates_username_uniqueness(self):
        """Registration should fail if username is taken."""
        create_user(username="existinguser")

        data = {
            "username": "existinguser",
            "email": "newuser@example.com",
            "password": TEST_PASSWORD,
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
            "password": TEST_PASSWORD,
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "email is already registered")

    def test_registration_rejects_reserved_username(self):
        """Reserved usernames (e.g., ``admin``, ``me``) are rejected.

        These names are reserved for sibling routes under ``/users/<username>/``;
        allowing them would silently shadow future routes.
        """
        data = {
            "username": "admin",
            "email": "newuser@example.com",
            "password": TEST_PASSWORD,
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username is reserved")
        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_registration_rejects_reserved_username_case_insensitive(self):
        """Reserved-name check is case-insensitive."""
        data = {
            "username": "Admin",
            "email": "newuser@example.com",
            "password": TEST_PASSWORD,
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username is reserved")

    def test_registration_validates_password_strength(self):
        """Registration should enforce password validation rules."""
        data = {
            "username": "newmaintainer",
            "email": "newuser@example.com",
            "password": "123",  # Too short and common
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, 200)
        # Django's password validators will catch this
        self.assertFalse(User.objects.filter(username="newmaintainer").exists())


@tag("views")
class InvitationClaimRaceTests(AccessControlTestCase):
    """One token, one account.

    The claim is a conditional UPDATE rather than ``select_for_update``,
    because dev runs on SQLite where Django raises ``NotSupportedError`` for
    row locking. These tests pin the behaviour that makes that safe.
    """

    def setUp(self):
        """Create an invitation and the form data to redeem it with."""
        self.invitation = Invitation.objects.create(email="newuser@example.com")
        self.register_url = reverse("invitation-register", kwargs={"token": self.invitation.token})
        self.data = {
            "username": "firstcomer",
            "email": "newuser@example.com",
            "password": TEST_PASSWORD,
        }

    def test_a_second_claim_creates_no_account(self):
        """Simulate the loser of the race: the invitation is already claimed.

        The view holds a stale in-memory invitation that still looks
        pending, exactly as the losing request would.
        """
        from flipfix.apps.accounts.forms import InvitationRegistrationForm
        from flipfix.apps.accounts.views.registration import _register

        stale = Invitation.objects.get(pk=self.invitation.pk)
        Invitation.objects.filter(pk=self.invitation.pk).update(accepted_at=timezone.now())

        form = InvitationRegistrationForm(self.data)
        self.assertTrue(form.is_valid())
        self.assertIsNone(_register(form, stale))
        self.assertFalse(User.objects.filter(username="firstcomer").exists())

    def test_the_token_cannot_be_redeemed_twice_over_http(self):
        """Second POST with the same token is rejected before any work."""
        self.client.post(self.register_url, self.data)

        second = Client()
        response = second.post(
            self.register_url,
            {**self.data, "username": "secondcomer", "email": "second@example.com"},
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))
        self.assertFalse(User.objects.filter(username="secondcomer").exists())
        self.assertEqual(Invitation.objects.filter(accepted_at__isnull=False).count(), 1)
