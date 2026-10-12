"""Tests for the send_test_email management command."""

from io import StringIO

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings, tag


@tag("commands")
class SendTestEmailCommandTests(SimpleTestCase):
    """The command exists to prove delivery, so it must never fake it."""

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_fails_without_sending_on_a_non_delivering_backend(self):
        """A "✓ Sent" after "nothing will reach the recipient" would contradict itself."""
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command("send_test_email", "someone@example.com", stdout=stdout)

        self.assertNotIn("Sent", stdout.getvalue())

    def test_sends_one_message_on_a_delivering_backend(self):
        """The test runner's locmem outbox stands in for a real provider."""
        stdout = StringIO()

        call_command("send_test_email", "someone@example.com", stdout=stdout)

        self.assertEqual([message.to for message in mail.outbox], [["someone@example.com"]])
        self.assertIn("Sent 1 message", stdout.getvalue())
