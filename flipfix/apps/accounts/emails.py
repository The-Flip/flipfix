"""Outbound email for the accounts domain.

Sending is synchronous and deliberately so. The obvious alternative is a
django-q task fired from ``transaction.on_commit``, but the invite page
shows the shareable link right next to the send: a *visible* failure lets
the inviter fall back to handing over the link, where a background failure
would report "Sent!" and strand the new volunteer in a worker log. It also
means invites work in development without ``make runq``.

The same reasoning rules out reporting success from a backend that delivers
nothing (see ``backend_delivers_mail``).

The cost is a bounded stall in the request cycle — see ``EMAIL_TIMEOUT`` in
``flipfix/settings/base.py``.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Invitation

logger = logging.getLogger(__name__)

SUBJECT = "You've been invited to Flipfix"

# Backends that accept a message and report success without delivering it.
# Fine for development; in production they make every invite look sent.
# locmem is deliberately absent: the test runner installs it and the tests
# assert on ``mail.outbox``, which is the delivery they care about.
NON_DELIVERING_BACKENDS = frozenset(
    {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
        "django.core.mail.backends.filebased.EmailBackend",
    }
)


class SendOutcome(Enum):
    """What happened to an invitation email, as the inviter needs to hear it."""

    SENT = auto()
    FAILED = auto()
    NOT_CONFIGURED = auto()


def backend_delivers_mail() -> bool:
    """Whether ``EMAIL_BACKEND`` actually delivers mail to recipients."""
    return settings.EMAIL_BACKEND not in NON_DELIVERING_BACKENDS


def build_registration_url(invitation: Invitation, request: HttpRequest) -> str:
    """Absolute, shareable registration URL for ``invitation``.

    Absolute because it goes into an email and onto a clipboard. This is
    the single place the link is built, so the emailed link and the copied
    link can never disagree.
    """
    path = reverse("invitation-register", kwargs={"token": invitation.token})
    return request.build_absolute_uri(path)


def send_invitation_email(invitation: Invitation, request: HttpRequest) -> SendOutcome:
    """Email the invitation link and report the outcome.

    Never raises: a failed send is a normal outcome the caller reports to
    the inviter alongside the copyable link, not an error page.

    With no delivering backend configured the message is not built at all.
    Handing it to the console backend would only write a live registration
    token into the service log, and the link is already on the page.
    """
    if not backend_delivers_mail():
        logger.warning(
            "invitation_email_skipped_backend_does_not_deliver",
            extra={"invitation_id": invitation.pk, "backend": settings.EMAIL_BACKEND},
        )
        return SendOutcome.NOT_CONFIGURED

    inviter = invitation.invited_by
    inviter_name = inviter.get_full_name() or inviter.get_username() if inviter else "A maintainer"
    body = render_to_string(
        "email/invitation.txt",
        {
            "inviter": inviter_name,
            "registration_url": build_registration_url(invitation, request),
            "expires_at": invitation.expires_at,
        },
    )
    try:
        send_mail(SUBJECT, body.strip() + "\n", None, [invitation.email], fail_silently=False)
    except (SMTPException, OSError):
        # OSError covers connection refused / DNS failure / timeout, which is
        # what a misconfigured or unreachable provider actually looks like.
        logger.exception("Failed to send invitation email", extra={"invitation_id": invitation.pk})
        return SendOutcome.FAILED
    return SendOutcome.SENT
