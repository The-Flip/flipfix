"""Outbound email for the accounts domain.

Sending is synchronous and deliberately so. The obvious alternative is a
django-q task fired from ``transaction.on_commit``, but the invite page
shows the shareable link right next to the send: a *visible* failure lets
the inviter fall back to handing over the link, where a background failure
would report "Sent!" and strand the new volunteer in a worker log. It also
means invites work in development without ``make runq``.

The cost is a bounded stall in the request cycle — see ``EMAIL_TIMEOUT`` in
``flipfix/settings/base.py``.
"""

from __future__ import annotations

import logging
from smtplib import SMTPException

from django.core.mail import send_mail
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Invitation

logger = logging.getLogger(__name__)

SUBJECT = "You've been invited to Flipfix"


def build_registration_url(invitation: Invitation, request: HttpRequest) -> str:
    """Absolute, shareable registration URL for ``invitation``.

    Absolute because it goes into an email and onto a clipboard. This is
    the single place the link is built, so the emailed link and the copied
    link can never disagree.
    """
    path = reverse("invitation-register", kwargs={"token": invitation.token})
    return request.build_absolute_uri(path)


def send_invitation_email(invitation: Invitation, request: HttpRequest) -> bool:
    """Email the invitation link. Return whether it was handed to the backend.

    Returns ``False`` rather than raising: a failed send is a normal outcome
    the caller reports to the inviter alongside the copyable link, not an
    error page.
    """
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
        return False
    return True
