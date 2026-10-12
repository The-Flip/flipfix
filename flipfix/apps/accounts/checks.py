"""System checks for the accounts domain."""

from __future__ import annotations

from django.conf import settings
from django.core import checks

from .emails import backend_delivers_mail


@checks.register()
def check_email_delivery(app_configs, **kwargs) -> list[checks.CheckMessage]:
    """Warn when a non-debug deployment cannot deliver invitation email.

    A Warning, not an Error: the deploy runs ``migrate``, which runs checks,
    and an Error there would take the whole site down over a missing email
    setting. Invitations still work without email — the link is copyable.
    Development (``DEBUG``) uses the console backend on purpose and is left
    alone.
    """
    if settings.DEBUG or backend_delivers_mail():
        return []
    return [
        checks.Warning(
            f"EMAIL_BACKEND is {settings.EMAIL_BACKEND}, which does not deliver mail. "
            "Invitation emails will not be sent.",
            hint="Set EMAIL_BACKEND and the EMAIL_HOST_* variables. See docs/Operations.md.",
            id="accounts.W001",
        )
    ]
