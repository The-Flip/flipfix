"""Tests for invitation email delivery and its failure path."""

from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.test import override_settings, tag
from django.urls import reverse

from flipfix.apps.accounts.models import Invitation
from flipfix.apps.core.test_utils import AccessControlTestCase, create_maintainer_user


@tag("views")
class InvitationEmailTests(AccessControlTestCase):
    """What actually lands in the recipient's inbox."""

    def setUp(self):
        """Log in a maintainer with a recognisable name."""
        self.inviter = create_maintainer_user(
            username="wrench", first_name="Dana", last_name="Silver"
        )
        self.client.force_login(self.inviter)

    def test_body_carries_an_absolute_registration_url(self):
        """A relative path in an email is useless — it must be clickable."""
        self.client.post(reverse("invite-create"), {"email": "new@example.com"})

        invitation = Invitation.objects.get(email="new@example.com")
        register_path = reverse("invitation-register", kwargs={"token": invitation.token})
        self.assertIn(f"http://testserver{register_path}", mail.outbox[0].body)

    def test_body_names_the_inviter(self):
        """The recipient needs to know who this is from, or it reads as spam."""
        self.client.post(reverse("invite-create"), {"email": "new@example.com"})

        self.assertIn("Dana Silver", mail.outbox[0].body)

    def test_body_states_the_expiry(self):
        """A link with a deadline should say so."""
        self.client.post(reverse("invite-create"), {"email": "new@example.com"})

        invitation = Invitation.objects.get(email="new@example.com")
        self.assertIn(invitation.expires_at.strftime("%Y"), mail.outbox[0].body)


@tag("views")
class InvitationEmailFailureTests(AccessControlTestCase):
    """A failed send must not lose the invitation.

    This is the whole reason sending is synchronous: the inviter finds out
    immediately and can fall back to the link on the page in front of them.
    """

    def setUp(self):
        """Log in a maintainer."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)

    def test_invitation_survives_a_delivery_failure(self):
        """The invitation is created even when the provider is unreachable."""
        with patch("flipfix.apps.accounts.emails.send_mail", side_effect=SMTPException("nope")):
            response = self.client.post(
                reverse("invite-create"), {"email": "new@example.com"}, follow=True
            )

        invitation = Invitation.objects.get(email="new@example.com")
        self.assertTrue(invitation.is_pending)
        self.assertRedirects(response, invitation.get_absolute_url())

    def test_failure_is_reported_with_the_fallback_instruction(self):
        """The inviter is told to send the link themselves."""
        with patch("flipfix.apps.accounts.emails.send_mail", side_effect=SMTPException("nope")):
            response = self.client.post(
                reverse("invite-create"), {"email": "new@example.com"}, follow=True
            )

        messages = [str(message) for message in response.context["messages"]]
        self.assertTrue(any("couldn't email" in message for message in messages))

    def test_last_sent_at_is_not_stamped_on_failure(self):
        """Nothing was sent, so the record must not claim otherwise."""
        with patch("flipfix.apps.accounts.emails.send_mail", side_effect=SMTPException("nope")):
            self.client.post(reverse("invite-create"), {"email": "new@example.com"})

        invitation = Invitation.objects.get(email="new@example.com")
        self.assertIsNone(invitation.last_sent_at)

    def test_connection_errors_are_handled_too(self):
        """A misconfigured host raises OSError, not SMTPException."""
        with patch(
            "flipfix.apps.accounts.emails.send_mail",
            side_effect=ConnectionRefusedError("no route"),
        ):
            self.client.post(reverse("invite-create"), {"email": "new@example.com"})

        self.assertTrue(Invitation.objects.filter(email="new@example.com").exists())


@tag("views")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class InvitationEmailNotConfiguredTests(AccessControlTestCase):
    """With no real backend configured, nothing is delivered — so say so.

    Regression: production ran for a week on the console backend, which
    "succeeds" by printing to the log. Every inviter was told "Invitation
    emailed" and no invitee received anything.
    """

    def setUp(self):
        """Log in a maintainer."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)

    def _invite(self):
        return self.client.post(reverse("invite-create"), {"email": "new@example.com"}, follow=True)

    def test_inviter_is_not_told_it_was_emailed(self):
        """The success message would be a lie."""
        response = self._invite()

        messages = [str(message) for message in response.context["messages"]]
        self.assertFalse(any("emailed" in message for message in messages))
        self.assertTrue(any("isn't set up" in message for message in messages))

    def test_last_sent_at_is_not_stamped(self):
        """Nothing was delivered, so the record must not claim otherwise."""
        self._invite()

        invitation = Invitation.objects.get(email="new@example.com")
        self.assertIsNone(invitation.last_sent_at)

    def test_message_is_not_handed_to_the_backend(self):
        """The console backend would write a live registration token into the log."""
        with patch("flipfix.apps.accounts.emails.send_mail") as send_mail:
            self._invite()

        send_mail.assert_not_called()

    def test_resend_is_not_reported_as_emailed_either(self):
        """Resend shares the reporting path, so it must not claim delivery."""
        invitation = Invitation.objects.create(email="old@example.com", invited_by=self.inviter)

        response = self.client.post(
            reverse("invite-resend", kwargs={"pk": invitation.pk}), follow=True
        )

        messages = [str(message) for message in response.context["messages"]]
        self.assertTrue(any("isn't set up" in message for message in messages))
        invitation.refresh_from_db()
        self.assertIsNone(invitation.last_sent_at)

    def test_invitation_is_still_created(self):
        """The link on the detail page is the fallback, so the invitation must exist."""
        self._invite()

        self.assertTrue(Invitation.objects.get(email="new@example.com").is_pending)
