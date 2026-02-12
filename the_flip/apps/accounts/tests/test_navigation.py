"""Tests for navigation display based on auth state."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import create_maintainer_user, create_user


@tag("views")
class NavigationTests(TestCase):
    """Tests for navigation display based on auth state."""

    def test_nav_shows_login_when_not_authenticated(self):
        """Navigation should show login link when not authenticated."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("login")}"')
        # When not authenticated, no avatar/dropdown should be present
        self.assertNotContains(response, 'class="avatar"')
        # Nav links should be hidden
        self.assertNotContains(response, f'href="{reverse("maintainer-machine-list")}"')
        self.assertNotContains(response, f'href="{reverse("problem-report-list")}"')
        self.assertNotContains(response, f'href="{reverse("log-list")}"')

    def test_nav_shows_user_menu_when_authenticated(self):
        """Navigation should show user menu when authenticated."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        # User dropdown should be present with avatar and profile link
        self.assertContains(response, 'class="avatar"')
        self.assertContains(response, f'href="{reverse("profile")}"')

    def test_nav_shows_initials_with_full_name(self):
        """Avatar should show both initials when first and last name are set."""
        user = create_user(username="testuser", first_name="John", last_name="Doe")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "JD")

    def test_nav_shows_first_initial_with_first_name_only(self):
        """Avatar should show first initial when only first name is set."""
        user = create_user(username="testuser", first_name="John")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('class="avatar"', content)
        # Should contain J but not JD
        self.assertIn(">J<", content.replace("\n", "").replace(" ", ""))

    def test_nav_shows_username_initial_with_no_name(self):
        """Avatar should show username initial when no name is set."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('class="avatar"', content)
        # Should contain T (first letter of testuser, uppercase)
        self.assertIn(">T<", content.replace("\n", "").replace(" ", ""))

    def test_nav_shows_links_for_maintainer(self):
        """Navigation should show nav links for users with maintainer permission."""
        user = create_maintainer_user(username="maintainer")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        # Nav links should be present
        self.assertContains(response, f'href="{reverse("maintainer-machine-list")}"')
        self.assertContains(response, f'href="{reverse("problem-report-list")}"')
        self.assertContains(response, f'href="{reverse("log-list")}"')

    def test_nav_hides_links_for_user_without_permission(self):
        """Navigation should hide nav links for authenticated users without permission."""
        user = create_user(username="regular")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        # User is logged in, so avatar should be present
        self.assertContains(response, 'class="avatar"')
        # But nav links should be hidden (no maintainer permission)
        self.assertNotContains(response, f'href="{reverse("maintainer-machine-list")}"')
        self.assertNotContains(response, f'href="{reverse("problem-report-list")}"')
        self.assertNotContains(response, f'href="{reverse("log-list")}"')

    def test_nav_shows_admin_dropdown_for_superuser(self):
        """Admin dropdown should be visible only for superusers."""
        superuser = create_user(username="admin", is_superuser=True, is_staff=True)
        self.client.force_login(superuser)
        response = self.client.get(reverse("home"))
        # Admin dropdown should contain admin-specific links
        self.assertContains(response, f'href="{reverse("wall-display-setup")}"')
        self.assertContains(response, f'href="{reverse("terminal-list")}"')
        self.assertContains(response, f'href="{reverse("admin:index")}"')

    def test_nav_hides_admin_dropdown_for_maintainer(self):
        """Admin dropdown should be hidden for non-superuser maintainers."""
        maintainer = create_maintainer_user(username="maintainer")
        self.client.force_login(maintainer)
        response = self.client.get(reverse("home"))
        # Admin dropdown links should not be present
        self.assertNotContains(response, f'href="{reverse("wall-display-setup")}"')
        self.assertNotContains(response, f'href="{reverse("terminal-list")}"')
        self.assertNotContains(response, f'href="{reverse("admin:index")}"')

    def test_nav_user_dropdown_displays_username(self):
        """User dropdown should display the username."""
        user = create_user(username="cooluser123", first_name="Cool", last_name="User")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "cooluser123")

    def test_nav_logout_button_present(self):
        """Logout button should be present in user dropdown."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, "Logout")

    def test_nav_account_link_present(self):
        """Account settings link should be present in user dropdown."""
        user = create_user(username="testuser")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("profile")}"')
        self.assertContains(response, "Account")

    def test_nav_active_link_highlighting_machines(self):
        """Active nav link should be highlighted on machines page."""
        user = create_maintainer_user(username="maintainer")
        self.client.force_login(user)
        response = self.client.get(reverse("maintainer-machine-list"))
        # Check that machines link has active class
        self.assertContains(response, "nav-link--active")

    def test_nav_wiki_link_present_for_maintainer(self):
        """Wiki link should be present in navigation for maintainers."""
        user = create_maintainer_user(username="maintainer")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("wiki-home")}"')
        self.assertContains(response, "Docs")

    def test_nav_parts_link_present_for_maintainer(self):
        """Parts link should be present in navigation for maintainers."""
        user = create_maintainer_user(username="maintainer")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("part-request-list")}"')
        self.assertContains(response, "Parts")