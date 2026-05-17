"""Tests for the ``user`` markdown link type and its directory scoping.

The ``user`` link type targets ``auth.User`` but is scoped to maintainers
visible in the user directory (active, in the Maintainers group, not a shared
account). These tests lock down the contract that authoring, render, autocomplete,
storage-to-authoring, and RecordReference syncing all agree on that scope.
"""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.markdown_links import (
    convert_authoring_to_storage,
    convert_storage_to_authoring,
    render_all_links,
    sync_references,
)
from flipfix.apps.core.models import RecordReference
from flipfix.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_machine,
    create_maintainer_user,
    create_user,
)
from flipfix.apps.maintenance.models import LogEntry


@tag("views")
class UserLinkHappyPathTests(TestCase):
    """Happy-path conversion and rendering for directory-visible users."""

    def setUp(self):
        super().setUp()
        self.user = create_maintainer_user(
            username="alice", first_name="Alice", last_name="Anderson"
        )
        self.machine = create_machine()

    def test_authoring_to_storage_converts_username_to_id(self):
        result = convert_authoring_to_storage("Thanks [[user:alice]] for fixing.")

        self.assertEqual(result, f"Thanks [[user:id:{self.user.pk}]] for fixing.")

    def test_storage_to_authoring_round_trips_to_username(self):
        result = convert_storage_to_authoring(f"Thanks [[user:id:{self.user.pk}]] for fixing.")

        self.assertEqual(result, "Thanks [[user:alice]] for fixing.")

    def test_render_uses_display_name_with_username(self):
        result = render_all_links(f"[[user:id:{self.user.pk}]]")

        url = reverse("user-profile", kwargs={"username": "alice"})
        self.assertEqual(result, f"[Alice Anderson (alice)]({url})")

    def test_render_uses_bare_username_when_no_name(self):
        bare = create_maintainer_user(username="bare")
        result = render_all_links(f"[[user:id:{bare.pk}]]")

        url = reverse("user-profile", kwargs={"username": "bare"})
        self.assertEqual(result, f"[bare]({url})")

    def test_hard_deleted_user_renders_as_broken_link(self):
        pk = self.user.pk
        self.user.delete()

        result = render_all_links(f"[[user:id:{pk}]]")

        self.assertIn("*[broken link]*", result)


@tag("views")
class UserLinkAutocompleteTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Autocomplete API behavior for ``type=user``."""

    def setUp(self):
        super().setUp()
        self.url = reverse("api-link-targets")

    def test_returns_directory_visible_user(self):
        self.client.force_login(self.maintainer_user)
        alice = create_maintainer_user(username="alice", first_name="Alice")

        response = self.client.get(self.url + "?type=user&q=alice")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        refs = [r["ref"] for r in data["results"]]
        self.assertIn(alice.username, refs)

    def test_result_shape_uses_username_ref_and_display_label(self):
        self.client.force_login(self.maintainer_user)
        alice = create_maintainer_user(username="alice", first_name="Alice", last_name="Anderson")

        response = self.client.get(self.url + "?type=user&q=alice")

        data = response.json()
        match = next((r for r in data["results"] if r["ref"] == "alice"), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["label"], "Alice Anderson (alice)")
        self.assertEqual(match["ref"], alice.username)

    def test_results_sort_by_recent_activity_then_alpha(self):
        """Recently-active maintainers surface above less-active or never-seen
        maintainers, and the alpha tiebreaker breaks ties among the never-seen.
        Mirrors the user-directory sort so the [[ picker matches what users
        see when browsing /users/.
        """
        self.client.force_login(self.maintainer_user)

        now = timezone.now()
        recent = create_maintainer_user(username="recent")
        stale = create_maintainer_user(username="stale")
        # "zoe" and "amy" stay never-seen (last_active_at=NULL) to verify
        # the alpha tiebreaker among the never-active tail.
        create_maintainer_user(username="zoe")
        create_maintainer_user(username="amy")

        Maintainer.objects.filter(user=recent).update(last_active_at=now)
        Maintainer.objects.filter(user=stale).update(last_active_at=now - timedelta(days=30))

        response = self.client.get(self.url + "?type=user&q=")
        refs = [r["ref"] for r in response.json()["results"]]

        # The four maintainers we created should appear in this relative order
        # within the full result set. Filter to just our test users to avoid
        # coupling to other directory members created by TestDataMixin.
        ours = [ref for ref in refs if ref in {"recent", "stale", "amy", "zoe"}]
        self.assertEqual(ours, ["recent", "stale", "amy", "zoe"])


@tag("views")
class UserLinkScopingTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Out-of-directory users are uniformly invisible to the user link type.

    For each non-directory variant, assert the same contract across:
    autocomplete API, save-time conversion, render-time resolution,
    storage-to-authoring conversion, and RecordReference syncing.
    """

    def setUp(self):
        super().setUp()
        self.api_url = reverse("api-link-targets")
        self.machine = create_machine()

    # ------------------------------------------------------------------
    # The four "out of scope" fixtures
    # ------------------------------------------------------------------

    def _inactive_user(self):
        user = create_maintainer_user(username="inactive")
        user.is_active = False
        user.save(update_fields=["is_active"])
        return user

    def _non_maintainer_user(self):
        # Has a Maintainer profile but is not in the Maintainers group.
        # Mirrors a user who's been demoted but not deleted.
        user = create_user(username="exmaintainer")
        Maintainer.objects.create(user=user)
        return user

    def _shared_account_user(self):
        user = create_maintainer_user(username="kiosk")
        Maintainer.objects.filter(user=user).update(is_shared_account=True)
        return user

    def _orphan_user(self):
        # User row with no Maintainer profile, despite being in the
        # Maintainers group — e.g. a hand-added user. The exclusion reason
        # is the missing Maintainer row: ``in_user_directory()`` queries
        # ``Maintainer.objects``, so a User without a Maintainer is invisible
        # regardless of group membership.
        user = create_user(username="orphan")
        Group.objects.get(name="Maintainers").user_set.add(user)
        return user

    def _all_out_of_scope_users(self):
        return [
            ("inactive", self._inactive_user()),
            ("non_maintainer", self._non_maintainer_user()),
            ("shared_account", self._shared_account_user()),
            ("orphan", self._orphan_user()),
        ]

    # ------------------------------------------------------------------
    # Contract assertions
    # ------------------------------------------------------------------

    def test_autocomplete_excludes_out_of_scope_users(self):
        self.client.force_login(self.maintainer_user)

        for label, user in self._all_out_of_scope_users():
            with self.subTest(case=label):
                response = self.client.get(self.api_url + f"?type=user&q={user.username}")
                refs = [r["ref"] for r in response.json()["results"]]
                self.assertNotIn(user.username, refs)

    def test_authoring_to_storage_raises_for_out_of_scope(self):
        for label, user in self._all_out_of_scope_users():
            with self.subTest(case=label):
                with self.assertRaises(ValidationError) as ctx:
                    convert_authoring_to_storage(f"Hi [[user:{user.username}]]")
                self.assertIn("User not found", str(ctx.exception))

    def test_render_treats_out_of_scope_as_broken_link(self):
        for label, user in self._all_out_of_scope_users():
            with self.subTest(case=label):
                result = render_all_links(f"[[user:id:{user.pk}]]")
                self.assertIn("*[broken link]*", result)

    def test_storage_to_authoring_leaves_out_of_scope_token_unchanged(self):
        """The critical invariant: storage→authoring refuses to materialise
        an out-of-scope slug. The edit form shows the raw token so the
        maintainer can decide what to do with it; broken-link text is
        strictly a render-time concern.
        """
        for label, user in self._all_out_of_scope_users():
            with self.subTest(case=label):
                token = f"[[user:id:{user.pk}]]"
                result = convert_storage_to_authoring(token)
                self.assertEqual(result, token)
                # Sanity: never produces broken-link text in authoring form
                self.assertNotIn("[broken link]", result)

    def test_sync_references_prunes_when_user_leaves_directory(self):
        """RecordReference rows track the scoped target set. A directory-
        visible user picks up a row when linked, and the row is pruned on
        the next save once they leave the directory. Restoring directory
        visibility re-creates the row (self-healing).
        """
        alice = create_maintainer_user(username="alice")
        source = LogEntry.objects.create(machine=self.machine, text="placeholder")
        content = f"Thanks [[user:id:{alice.pk}]]!"

        # 1. Initial sync creates the row.
        sync_references(source, content)
        user_ct = ContentType.objects.get(app_label="auth", model="user")
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=ContentType.objects.get_for_model(source),
                source_id=source.pk,
                target_type=user_ct,
                target_id=alice.pk,
            ).exists()
        )

        # 2. Alice leaves the directory; same content re-syncs to nothing.
        alice.is_active = False
        alice.save(update_fields=["is_active"])
        sync_references(source, content)
        self.assertFalse(
            RecordReference.objects.filter(
                source_type=ContentType.objects.get_for_model(source),
                source_id=source.pk,
                target_type=user_ct,
                target_id=alice.pk,
            ).exists()
        )

        # 3. Restore alice; the row comes back on the next save.
        alice.is_active = True
        alice.save(update_fields=["is_active"])
        sync_references(source, content)
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=ContentType.objects.get_for_model(source),
                source_id=source.pk,
                target_type=user_ct,
                target_id=alice.pk,
            ).exists()
        )
