"""Tests for accounts.display helpers."""

from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase, tag

from flipfix.apps.accounts.display import display_name_with_username


@tag("unit")
class DisplayNameWithUsernameTests(SimpleTestCase):
    """Format ``display_name_with_username`` produces for various inputs."""

    def test_no_name_returns_bare_username(self):
        user = SimpleNamespace(first_name="", last_name="", username="alice")
        self.assertEqual(display_name_with_username(user), "alice")

    def test_both_names_returns_full_with_username(self):
        user = SimpleNamespace(first_name="Alice", last_name="Anderson", username="alice")
        self.assertEqual(display_name_with_username(user), "Alice Anderson (alice)")

    def test_first_name_only(self):
        user = SimpleNamespace(first_name="Alice", last_name="", username="alice")
        self.assertEqual(display_name_with_username(user), "Alice (alice)")

    def test_last_name_only(self):
        user = SimpleNamespace(first_name="", last_name="Anderson", username="alice")
        self.assertEqual(display_name_with_username(user), "Anderson (alice)")

    def test_none_user_returns_empty_string(self):
        self.assertEqual(display_name_with_username(None), "")

    def test_works_on_real_user_instance(self):
        """Sanity check against the actual User model, not just duck types."""
        user = User(username="bob", first_name="Bob", last_name="Brown")
        self.assertEqual(display_name_with_username(user), "Bob Brown (bob)")
