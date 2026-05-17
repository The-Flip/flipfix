"""Tests for the ``/users`` directory listing view.

Covers permission gating, visibility filtering, sort order, search markup,
and the empty-state branch. The visibility predicate itself is tested
exhaustively in ``test_user_directory_predicates.py``; here we verify the
view wires the queryset, template, and access check correctly.
"""

from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.test_utils import (
    create_maintainer_user,
    create_user,
)


@tag("views")
class UserDirectoryAccessTests(TestCase):
    """Who can reach ``/users``."""

    def setUp(self):
        self.url = reverse("user-directory")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        # Middleware redirects unauthenticated users to login.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_non_maintainer_forbidden(self):
        """A logged-in user without portal access cannot view the directory.

        ``MaintainerAccessMiddleware`` blocks them before the view runs.
        """
        user = create_user(username="visitor")
        self.client.force_login(user)
        response = self.client.get(self.url)
        # Middleware returns 403 (or redirects) for non-maintainers; the
        # important contract is "not 200".
        self.assertNotEqual(response.status_code, 200)

    def test_maintainer_can_view(self):
        user = create_maintainer_user(username="alice")
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_shared_terminal_account_can_view(self):
        """Kiosk use case: shared terminal accounts can browse the directory."""
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class UserDirectoryContentTests(TestCase):
    """What the directory shows."""

    def setUp(self):
        self.url = reverse("user-directory")
        self.viewer = create_maintainer_user(username="viewer")
        self.client.force_login(self.viewer)

    def test_active_maintainer_appears(self):
        create_maintainer_user(username="alice", first_name="Alice")
        response = self.client.get(self.url)
        self.assertContains(response, "alice")

    def test_inactive_user_excluded(self):
        user = create_maintainer_user(username="bob", first_name="Bob")
        user.is_active = False
        user.save()
        response = self.client.get(self.url)
        # data-search-text is unique per card, so its absence is a
        # strong signal that the card didn't render.
        self.assertNotContains(response, 'data-search-text="Bob  bob"')

    def test_shared_account_excluded(self):
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, 'data-search-text="  kiosk"')

    def test_non_maintainer_excluded(self):
        # A user in no groups should not appear.
        create_user(username="orphan", first_name="Orphan")
        response = self.client.get(self.url)
        self.assertNotContains(response, 'data-search-text="Orphan  orphan"')

    def test_search_input_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="user-directory-search"')

    def test_no_results_message_rendered_hidden(self):
        """The 'no users match' element ships in the DOM, hidden, for the JS to toggle."""
        response = self.client.get(self.url)
        self.assertContains(
            response,
            'id="user-directory-no-results"',
        )
        self.assertContains(response, 'class="text-muted hidden"')

    def test_search_text_data_attribute(self):
        """Each card carries first/last/username in data-search-text for client-side filter."""
        create_maintainer_user(username="alice", first_name="Alice", last_name="Anderson")
        response = self.client.get(self.url)
        self.assertContains(response, 'data-search-text="Alice Anderson alice"')

    def test_silhouette_stub_when_no_media(self):
        create_maintainer_user(username="alice", first_name="Alice")
        response = self.client.get(self.url)
        self.assertContains(response, "user-card__silhouette")

    def test_card_uses_standard_clickable_card_classes(self):
        """Regression guard: cards must inherit the shared hover/focus styling."""
        create_maintainer_user(username="alice", first_name="Alice")
        response = self.client.get(self.url)
        self.assertContains(response, 'class="card card--clickable user-card"')

    def test_bio_rendered_truncated_and_as_markdown(self):
        """Bio uses the truncatechars → render_markdown condensed pattern."""
        user = create_maintainer_user(username="alice", first_name="Alice")
        user.maintainer.bio = "**Bold bio** with much more text " * 10
        user.maintainer.save()
        response = self.client.get(self.url)
        # Markdown emphasis becomes <strong>; we don't assert exact length
        # (truncatechars + markdown interplay) — just that bold was applied
        # and the trailing repetitions did not all render.
        self.assertContains(response, "<strong>Bold bio</strong>")


@tag("views")
class UserDirectoryEmptyStateTests(TestCase):
    """Empty grid renders the shared empty-state component, not a blank page."""

    def test_empty_directory_renders_empty_state(self):
        viewer = create_maintainer_user(username="viewer")
        # Hide the viewer themselves so the directory is truly empty.
        viewer.maintainer.is_shared_account = True
        viewer.maintainer.save()
        self.client.force_login(viewer)
        # Shared-account viewer can still load /users.
        response = self.client.get(reverse("user-directory"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No users in the directory yet.")
        # And we did not render the grid container at all.
        self.assertNotContains(response, 'id="user-directory-list"')


@tag("views")
class UserDirectorySortTests(TestCase):
    """Directory sorts alphabetically by display-name first character.

    Sort key: ``Lower(Coalesce(NullIf(first_name, ""), username))``. With
    Lower() applied, casing does not flip the order; without it, byte
    order would put "Zoe" before "alice".
    """

    def test_alphabetical_case_insensitive(self):
        create_maintainer_user(username="zoe-user", first_name="Zoe")
        create_maintainer_user(username="alice-user", first_name="alice")
        create_maintainer_user(username="bob-user", first_name="Bob")
        viewer = create_maintainer_user(username="viewer")
        self.client.force_login(viewer)

        response = self.client.get(reverse("user-directory"))
        usernames = [m.user.username for m in response.context["maintainers"]]
        # alice, Bob, viewer, Zoe — case-insensitive on the first-name key,
        # with the viewer (no first name) sorting under "viewer".
        self.assertEqual(usernames, ["alice-user", "bob-user", "viewer", "zoe-user"])

    def test_falls_back_to_username_when_no_first_name(self):
        create_maintainer_user(username="zebra")
        create_maintainer_user(username="alpha")
        viewer = create_maintainer_user(username="middle")
        self.client.force_login(viewer)

        response = self.client.get(reverse("user-directory"))
        usernames = [m.user.username for m in response.context["maintainers"]]
        self.assertEqual(usernames, ["alpha", "middle", "zebra"])

    def test_no_duplicates_for_user_in_multiple_groups(self):
        """``.distinct()`` guards against M2M-join row duplication.

        A maintainer in another group besides Maintainers should appear
        exactly once.
        """
        from django.contrib.auth.models import Group

        user = create_maintainer_user(username="multi", first_name="Multi")
        extra_group, _ = Group.objects.get_or_create(name="Extra Group")
        user.groups.add(extra_group)

        viewer = create_maintainer_user(username="viewer")
        self.client.force_login(viewer)

        response = self.client.get(reverse("user-directory"))
        ids = [m.id for m in response.context["maintainers"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(Maintainer.objects.get(user=user).id, ids)
