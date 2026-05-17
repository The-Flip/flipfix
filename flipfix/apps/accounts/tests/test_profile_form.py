"""Tests for ``MaintainerProfileForm`` (the bio editor).

Covers the markdown-link conversion hook on the bio field.
"""

from django.test import TestCase, tag

from flipfix.apps.accounts.forms import MaintainerProfileForm, TerminalCreateForm
from flipfix.apps.core.test_utils import create_maintainer_user


@tag("forms")
class MaintainerProfileFormTests(TestCase):
    def test_blank_bio_is_valid(self):
        user = create_maintainer_user(username="alice")
        form = MaintainerProfileForm(data={"bio": ""}, instance=user.maintainer)
        self.assertTrue(form.is_valid(), form.errors)

    def test_short_bio_saves(self):
        user = create_maintainer_user(username="alice")
        form = MaintainerProfileForm(
            data={"bio": "Hello, I fix pinball."}, instance=user.maintainer
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.maintainer.refresh_from_db()
        self.assertEqual(user.maintainer.bio, "Hello, I fix pinball.")

    def test_clean_bio_rejects_unresolvable_authoring_links(self):
        """``clean_markdown_field`` hook runs on bio.

        Authoring-format ``[[type:label]]`` links that don't resolve are
        rejected at form-clean time — same behavior as problem-report
        descriptions. This confirms the hook is wired; conversion mechanics
        are tested under ``core.markdown_links``.
        """
        user = create_maintainer_user(username="alice")
        form = MaintainerProfileForm(
            data={"bio": "See [[machine:Nonexistent]] for context."},
            instance=user.maintainer,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("bio", form.errors)


@tag("forms")
class TerminalCreateFormReservedUsernameTests(TestCase):
    """Reserved usernames are rejected by ``TerminalCreateForm`` as well.

    The ``InvitationRegistrationForm`` is covered end-to-end in
    ``test_registration.py``; covering the terminal form unit-level here
    confirms both registration paths share the protection.
    """

    def test_rejects_reserved_username(self):
        form = TerminalCreateForm(data={"username": "admin"})
        self.assertFalse(form.is_valid())
        self.assertIn("username is reserved", str(form.errors["username"]))

    def test_rejects_reserved_username_case_insensitive(self):
        form = TerminalCreateForm(data={"username": "ADMIN"})
        self.assertFalse(form.is_valid())
        self.assertIn("username is reserved", str(form.errors["username"]))

    def test_normal_username_accepted(self):
        form = TerminalCreateForm(data={"username": "workshop-terminal"})
        self.assertTrue(form.is_valid(), form.errors)
