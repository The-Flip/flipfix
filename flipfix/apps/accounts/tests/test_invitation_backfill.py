"""Tests for the attribution rule in migration 0015.

The backfill guesses ``accepted_by`` for historical invitations by matching
the invitation's email to a user's. That guess is the one place this feature
can silently credit the wrong person, so the rule gets its own test.

Only the rule is tested, not the migration run: exercising a historical
migration needs a ``TransactionTestCase``, which truncates every table —
and this project seeds the Maintainers group from a data migration, so that
would leave the developer's persistent test database broken for the next
run. The rule is where the risk lives; the loop around it is three lines.
"""

import importlib

from django.test import SimpleTestCase, tag

migration = importlib.import_module(
    "flipfix.apps.accounts.migrations.0015_backfill_invitation_acceptance"
)


@tag("models")
class PickAcceptedByTests(SimpleTestCase):
    """ "Exactly one match, or nobody."""

    def test_a_single_match_is_used(self):
        """One user with that address: safe to credit them."""
        self.assertEqual(migration.pick_accepted_by(["only"]), "only")

    def test_no_match_yields_none(self):
        """Nobody matches, so nobody is credited."""
        self.assertIsNone(migration.pick_accepted_by([]))

    def test_an_ambiguous_match_yields_none(self):
        """Two users share the address, so we do not choose between them.

        An invite tree that says "unknown" is honest. One that names the
        wrong person is worse than one that names nobody.
        """
        self.assertIsNone(migration.pick_accepted_by(["one", "two"]))
