"""Tests for the system check that flags undeliverable email settings."""

from django.core.checks import WARNING
from django.test import SimpleTestCase, override_settings, tag

from flipfix.apps.accounts.checks import check_email_delivery

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


@tag("unit")
class EmailDeliveryCheckTests(SimpleTestCase):
    """Production must not silently run on a backend that delivers nothing."""

    @override_settings(DEBUG=False, EMAIL_BACKEND=CONSOLE)
    def test_warns_when_production_uses_the_console_backend(self):
        """The exact misconfiguration that stranded a week of invitations."""
        warnings = check_email_delivery(app_configs=None)

        self.assertEqual([warning.id for warning in warnings], ["accounts.W001"])
        self.assertEqual(warnings[0].level, WARNING)

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_warns_for_the_dummy_backend_too(self):
        """Any backend that discards mail is the same problem."""
        self.assertEqual(len(check_email_delivery(app_configs=None)), 1)

    @override_settings(DEBUG=False, EMAIL_BACKEND=SMTP)
    def test_silent_when_a_real_backend_is_configured(self):
        """Configured production raises nothing."""
        self.assertEqual(check_email_delivery(app_configs=None), [])

    @override_settings(DEBUG=True, EMAIL_BACKEND=CONSOLE)
    def test_silent_in_development(self):
        """The console backend is the intended default when developing."""
        self.assertEqual(check_email_delivery(app_configs=None), [])
