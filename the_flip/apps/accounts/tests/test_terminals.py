"""Tests for shared terminal account views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_shared_terminal,
    create_staff_user,
    create_superuser,
    create_user,
)

User = get_user_model()


class TerminalTestMixin:
    """Mixin providing common setup for terminal tests."""

    def setUp(self):
        super().setUp()
        self.superuser = create_superuser(username="admin")
        self.terminal = create_shared_terminal(
            username="workshop-terminal", first_name="Workshop", last_name="Terminal"
        )


@tag("views", "terminals")
class TerminalListViewTests(TerminalTestMixin, TestCase):
    """Tests for the terminal list view."""

    def setUp(self):
        super().setUp()
        self.staff_user = create_staff_user(username="staffuser")
        self.list_url = reverse("terminal-list")

    def test_requires_superuser(self):
        """Terminal list should require superuser access."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal list."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_list.html")

    def test_lists_shared_terminals(self):
        """Terminal list should show shared terminal accounts."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "Workshop Terminal")

    def test_shows_deactivated_label(self):
        """Deactivated terminals should show (deactivated) label."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "(deactivated)")

    def test_empty_state(self):
        """Should show message when no terminals exist."""
        self.terminal.delete()

        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertContains(response, "No shared terminal accounts have been created yet")


@tag("views", "terminals")
class TerminalLoginViewTests(TerminalTestMixin, TestCase):
    """Tests for the terminal login view."""

    def setUp(self):
        super().setUp()
        self.login_url = reverse("terminal-login", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal login should require POST request."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 405)

    def test_superuser_can_login_as_terminal(self):
        """Superuser should be able to log in as terminal."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.login_url, follow=True)

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(response.context["user"].username, "workshop-terminal")

    def test_shows_success_message(self):
        """Login should show success message."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.login_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Logged in as", str(messages[0]))

    def test_cannot_login_to_deactivated_terminal(self):
        """Should not be able to log in to deactivated terminal."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.login_url)
        self.assertEqual(response.status_code, 404)


@tag("views", "terminals")
class TerminalCreateViewTests(TestCase):
    """Tests for the terminal create view."""

    def setUp(self):
        self.superuser = create_superuser(username="admin")
        self.add_url = reverse("terminal-add")

    def test_requires_superuser(self):
        """Terminal create should require superuser access."""
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal create page."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_form.html")

    def test_creates_terminal(self):
        """Should create a shared terminal account."""
        self.client.login(username="admin", password="testpass123")
        data = {"username": "new-terminal", "first_name": "New", "last_name": "Terminal"}
        response = self.client.post(self.add_url, data, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        user = User.objects.get(username="new-terminal")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Terminal")
        self.assertTrue(user.is_staff)

        maintainer = Maintainer.objects.get(user=user)
        self.assertTrue(maintainer.is_shared_account)

    def test_validates_username_uniqueness(self):
        """Should reject duplicate usernames."""
        create_user(username="existing")

        self.client.login(username="admin", password="testpass123")
        data = {"username": "existing"}
        response = self.client.post(self.add_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")

    def test_form_has_password_manager_protection(self):
        """Form should have attributes to prevent password manager autofill."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.add_url)

        self.assertContains(response, 'autocomplete="off"')
        self.assertContains(response, "data-1p-ignore")
        self.assertContains(response, 'data-lpignore="true"')


@tag("views", "terminals")
class TerminalUpdateViewTests(TerminalTestMixin, TestCase):
    """Tests for the terminal update view."""

    def setUp(self):
        super().setUp()
        self.edit_url = reverse("terminal-edit", kwargs={"pk": self.terminal.pk})

    def test_requires_superuser(self):
        """Terminal edit should require superuser access."""
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_access(self):
        """Superuser should be able to access terminal edit page."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/terminal_form.html")

    def test_prefills_form_data(self):
        """Form should be prefilled with current data."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, 'value="Workshop"')
        self.assertContains(response, 'value="Terminal"')

    def test_shows_username_as_readonly(self):
        """Username should be displayed but not editable."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "workshop-terminal")
        self.assertNotContains(response, 'name="username"')

    def test_updates_terminal(self):
        """Should update terminal's first/last name."""
        self.client.login(username="admin", password="testpass123")
        data = {"first_name": "Updated", "last_name": "Name"}
        response = self.client.post(self.edit_url, data, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertEqual(self.terminal.user.first_name, "Updated")
        self.assertEqual(self.terminal.user.last_name, "Name")

    def test_shows_deactivate_button_for_active_terminal(self):
        """Should show deactivate button for active terminals."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "Deactivate")

    def test_hides_deactivate_button_for_inactive_terminal(self):
        """Should hide deactivate button for inactive terminals."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertNotContains(response, "Deactivate")

    def test_shows_reactivate_button_for_inactive_terminal(self):
        """Should show re-activate button for inactive terminals."""
        self.terminal.user.is_active = False
        self.terminal.user.save()

        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.edit_url)
        self.assertContains(response, "Re-activate")


@tag("views", "terminals")
class TerminalDeactivateViewTests(TerminalTestMixin, TestCase):
    """Tests for the terminal deactivate view."""

    def setUp(self):
        super().setUp()
        self.deactivate_url = reverse("terminal-deactivate", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal deactivate should require POST request."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.deactivate_url)
        self.assertEqual(response.status_code, 405)

    def test_deactivates_terminal(self):
        """Should deactivate terminal account."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.deactivate_url, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertFalse(self.terminal.user.is_active)

    def test_shows_success_message(self):
        """Deactivate should show success message."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.deactivate_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("deactivated", str(messages[0]))


@tag("views", "terminals")
class TerminalReactivateViewTests(TestCase):
    """Tests for the terminal reactivate view."""

    def setUp(self):
        self.superuser = create_superuser(username="admin")
        self.terminal = create_shared_terminal(
            username="workshop-terminal", first_name="Workshop", last_name="Terminal"
        )
        self.terminal.user.is_active = False
        self.terminal.user.save()
        self.reactivate_url = reverse("terminal-reactivate", kwargs={"pk": self.terminal.pk})

    def test_requires_post(self):
        """Terminal reactivate should require POST request."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.reactivate_url)
        self.assertEqual(response.status_code, 405)

    def test_reactivates_terminal(self):
        """Should reactivate terminal account."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.reactivate_url, follow=True)

        self.assertRedirects(response, reverse("terminal-list"))

        self.terminal.user.refresh_from_db()
        self.assertTrue(self.terminal.user.is_active)

    def test_shows_success_message(self):
        """Reactivate should show success message."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.post(self.reactivate_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("reactivated", str(messages[0]))
