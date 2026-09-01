"""Send a test email, to verify the configured provider before it matters.

Invitation delivery is the only thing that sends mail, and finding out it
is misconfigured while a volunteer waits at the workbench is the wrong time.
Run this after setting the EMAIL_* variables on a new environment.
"""

from __future__ import annotations

from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


class Command(BaseCommand):
    help = "Send a test email to verify the configured email backend"

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Address to send the test message to")

    def handle(self, *args, **options):
        self._report_config()
        self._send(options["recipient"])

    def _report_config(self):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"Backend:   {backend}")
        self.stdout.write(f"Host:      {settings.EMAIL_HOST or '(unset)'}:{settings.EMAIL_PORT}")
        self.stdout.write(f"TLS:       {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"From:      {settings.DEFAULT_FROM_EMAIL}")
        if backend == CONSOLE_BACKEND:
            self.stdout.write(
                self.style.WARNING(
                    "⚠ Console backend — the message below is printed, not delivered. "
                    "Set EMAIL_BACKEND and the EMAIL_HOST_* variables to send for real."
                )
            )

    def _send(self, recipient: str):
        try:
            sent = send_mail(
                "Flipfix test email",
                "This is a test message from Flipfix. If you received it, "
                "invitation email is working.\n",
                None,
                [recipient],
                fail_silently=False,
            )
        except (SMTPException, OSError) as exc:
            raise CommandError(f"✗ Send failed: {exc}") from exc

        if not sent:
            raise CommandError("✗ The backend accepted the call but sent 0 messages.")
        self.stdout.write(self.style.SUCCESS(f"✓ Sent 1 message to {recipient}"))
