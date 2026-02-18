"""Tests for nav_tags template tag helpers and rendered output."""

from __future__ import annotations

from django.template import RequestContext, Template
from django.test import RequestFactory, TestCase, tag
from django.urls import ResolverMatch

from flipfix.apps.core.templatetags.nav_tags import (
    ADMIN_NAV_ITEMS,
    MAIN_NAV_ITEMS,
    _get_url_name,
    _is_active,
    _resolve_admin_items,
    _resolve_nav_items,
)
from flipfix.apps.core.test_utils import create_maintainer_user, create_superuser, create_user


def _make_request(url_name: str = "", user=None):
    """Build a fake request with resolver_match.url_name set."""
    factory = RequestFactory()
    request = factory.get("/fake/")
    request.resolver_match = ResolverMatch(lambda: None, (), {}, url_name=url_name)
    if user is not None:
        request.user = user
    return request


# =============================================================================
# Layer 1: Helper unit tests
# =============================================================================


@tag("views")
class IsActiveTests(TestCase):
    """Tests for _is_active helper."""

    def test_exact_match_primary_route(self):
        """Machines item is active on maintainer-machine-list."""
        machines = MAIN_NAV_ITEMS[0]
        self.assertTrue(_is_active(machines, "maintainer-machine-list"))

    def test_exact_match_secondary_route(self):
        """Machines item is active on maintainer-machine-detail."""
        machines = MAIN_NAV_ITEMS[0]
        self.assertTrue(_is_active(machines, "maintainer-machine-detail"))

    def test_exact_match_inactive(self):
        """Machines item is not active on unrelated routes."""
        machines = MAIN_NAV_ITEMS[0]
        self.assertFalse(_is_active(machines, "problem-report-list"))

    def test_contains_match_active(self):
        """Problems item is active when url_name contains 'problem'."""
        problems = MAIN_NAV_ITEMS[1]
        self.assertTrue(_is_active(problems, "problem-report-list"))
        self.assertTrue(_is_active(problems, "problem-report-detail"))

    def test_contains_match_inactive(self):
        """Problems item is not active on unrelated routes."""
        problems = MAIN_NAV_ITEMS[1]
        self.assertFalse(_is_active(problems, "log-list"))

    def test_empty_url_name_activates_nothing(self):
        """No item is active when url_name is empty."""
        for item in MAIN_NAV_ITEMS:
            self.assertFalse(_is_active(item, ""), msg=f"{item.label} should not be active")


@tag("views")
class GetUrlNameTests(TestCase):
    """Tests for _get_url_name helper."""

    def test_none_url_name_returns_empty_string(self):
        """Unnamed URL patterns (url_name=None) return empty string, not None."""
        factory = RequestFactory()
        request = factory.get("/fake/")
        request.resolver_match = ResolverMatch(lambda: None, (), {}, url_name=None)
        context = {"request": request}
        self.assertEqual(_get_url_name(context), "")


# =============================================================================
# Layer 2: Route contract and resolver tests
# =============================================================================


@tag("views")
class RouteContractTests(TestCase):
    """Assert known URL names map to the correct active nav section.

    These tests document the active-state matching contract and will catch
    regressions if URL names are renamed or the matching rules change.
    """

    def _active_labels(self, url_name: str) -> set[str]:
        """Return set of nav item labels that are active for a given url_name."""
        items = _resolve_nav_items(url_name)
        return {str(item["label"]) for item in items if item["is_active"]}

    def test_machine_list(self):
        self.assertEqual(self._active_labels("maintainer-machine-list"), {"Machines"})

    def test_machine_detail(self):
        self.assertEqual(self._active_labels("maintainer-machine-detail"), {"Machines"})

    def test_problem_report_list(self):
        self.assertEqual(self._active_labels("problem-report-list"), {"Problems"})

    def test_problem_report_detail(self):
        self.assertEqual(self._active_labels("problem-report-detail"), {"Problems"})

    def test_log_list(self):
        self.assertEqual(self._active_labels("log-list"), {"Logs"})

    def test_log_detail(self):
        self.assertEqual(self._active_labels("log-detail"), {"Logs"})

    def test_logout_does_not_activate_logs(self):
        """'logout' should NOT match 'log-' (the hyphen is intentional)."""
        self.assertNotIn("Logs", self._active_labels("logout"))

    def test_login_does_not_activate_logs(self):
        """'login' should NOT match 'log-'."""
        self.assertNotIn("Logs", self._active_labels("login"))

    def test_part_request_list(self):
        self.assertEqual(self._active_labels("part-request-list"), {"Parts"})

    def test_wiki_home(self):
        self.assertEqual(self._active_labels("wiki-home"), {"Docs"})

    def test_wiki_page(self):
        self.assertEqual(self._active_labels("wiki-page"), {"Docs"})

    def test_empty_url_name(self):
        self.assertEqual(self._active_labels(""), set())

    def test_unrelated_route(self):
        self.assertEqual(self._active_labels("profile"), set())


@tag("views")
class ResolveNavItemsTests(TestCase):
    """Tests for _resolve_nav_items helper."""

    def test_returns_all_items(self):
        """Returns a dict for each item in MAIN_NAV_ITEMS."""
        result = _resolve_nav_items("problem-report-list")
        self.assertEqual(len(result), len(MAIN_NAV_ITEMS))

    def test_single_item_active(self):
        """Only the matching item has is_active=True."""
        result = _resolve_nav_items("problem-report-list")
        active = [item for item in result if item["is_active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["label"], "Problems")

    def test_docs_not_in_mobile_bar(self):
        """Docs item has in_mobile_bar=False."""
        result = _resolve_nav_items("")
        docs = next(item for item in result if item["label"] == "Docs")
        self.assertFalse(docs["in_mobile_bar"])

    def test_logs_has_mobile_extra_class(self):
        """Logs item has the --logs mobile extra class."""
        result = _resolve_nav_items("")
        logs = next(item for item in result if item["label"] == "Logs")
        self.assertEqual(logs["mobile_extra_class"], "nav-priority__item--logs")

    def test_parts_has_mobile_extra_class(self):
        """Parts item has the --parts mobile extra class."""
        result = _resolve_nav_items("")
        parts = next(item for item in result if item["label"] == "Parts")
        self.assertEqual(parts["mobile_extra_class"], "nav-priority__item--parts")


@tag("views")
class ResolveAdminItemsTests(TestCase):
    """Tests for _resolve_admin_items helper."""

    def test_returns_all_admin_items(self):
        """Returns a dict for each item in ADMIN_NAV_ITEMS."""
        result = _resolve_admin_items("")
        self.assertEqual(len(result), len(ADMIN_NAV_ITEMS))

    def test_tracked_item_active(self):
        """Wall Display is active when on its route."""
        result = _resolve_admin_items("wall-display-setup")
        wall = next(item for item in result if item["label"] == "Wall Display")
        self.assertTrue(wall["is_active"])

    def test_untracked_item_never_active(self):
        """Locations never shows as active (track_active=False)."""
        result = _resolve_admin_items("admin:catalog_location_changelist")
        locations = next(item for item in result if item["label"] == "Locations")
        self.assertFalse(locations["is_active"])

    def test_site_settings_present(self):
        """Site Settings appears in admin items."""
        result = _resolve_admin_items("")
        labels = [item["label"] for item in result]
        self.assertIn("Site Settings", labels)

    def test_site_settings_after_qr_codes_before_django_admin(self):
        """Site Settings is positioned after QR Codes and before Django Admin."""
        labels = [item.label for item in ADMIN_NAV_ITEMS]
        qr_idx = labels.index("QR Codes")
        settings_idx = labels.index("Site Settings")
        admin_idx = labels.index("Django Admin")
        self.assertEqual(settings_idx, qr_idx + 1)
        self.assertEqual(admin_idx, settings_idx + 1)

    def test_site_settings_active_on_its_route(self):
        """Site Settings is active when on site-settings route."""
        result = _resolve_admin_items("site-settings")
        site_settings = next(item for item in result if item["label"] == "Site Settings")
        self.assertTrue(site_settings["is_active"])

    def test_no_admin_active_on_unrelated_route(self):
        """No admin item is active on an unrelated route."""
        result = _resolve_admin_items("problem-report-list")
        active = [item for item in result if item["is_active"]]
        self.assertEqual(len(active), 0)


# =============================================================================
# Layer 3: Rendered HTML tests
# =============================================================================


def _render_tag(tag_call: str, request) -> str:
    """Render a nav tag and return the HTML string."""
    template = Template(f"{{% load nav_tags %}}{tag_call}")
    context = RequestContext(request)
    return template.render(context)


@tag("views")
class DesktopNavRenderTests(TestCase):
    """Rendered HTML assertions for {% desktop_nav %}."""

    def setUp(self):
        self.user = create_maintainer_user(username="navtest")

    def test_active_item_has_active_class(self):
        """Active nav item gets nav-link--active."""
        request = _make_request("problem-report-list", user=self.user)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn("nav-link--active", html)

    def test_active_item_has_aria_current(self):
        """Active nav item gets aria-current='page'."""
        request = _make_request("problem-report-list", user=self.user)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn('aria-current="page"', html)

    def test_inactive_items_no_active_class(self):
        """When on Problems page, Machines link is not active."""
        request = _make_request("problem-report-list", user=self.user)
        html = _render_tag("{% desktop_nav %}", request)
        # Count occurrences - should be exactly 1 active link
        self.assertEqual(html.count("nav-link--active"), 1)

    def test_all_nav_items_present(self):
        """All 5 nav items render in desktop nav."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% desktop_nav %}", request)
        for label in ("Machines", "Problems", "Logs", "Parts", "Docs"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_admin_dropdown_for_superuser(self):
        """Superuser sees admin dropdown."""
        superuser = create_superuser(username="navadmin")
        request = _make_request("", user=superuser)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn("Admin", html)
        self.assertIn("Wall Display", html)

    def test_admin_button_active_on_admin_route(self):
        """Admin dropdown button gets nav-link--active on admin routes."""
        superuser = create_superuser(username="adminbtnactive")
        request = _make_request("terminal-list", user=superuser)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn("dropdown__toggle nav-link--active", html)

    def test_admin_item_selected_on_its_route(self):
        """Terminals dropdown item gets dropdown__item--selected on terminal-list."""
        superuser = create_superuser(username="adminitemactive")
        request = _make_request("terminal-list", user=superuser)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn("dropdown__item--selected", html)

    def test_no_admin_for_regular_maintainer(self):
        """Regular maintainer does not see admin dropdown."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertNotIn("Wall Display", html)

    def test_public_nav_without_permission(self):
        """Non-maintainer user sees public nav items only."""
        regular = create_user(username="nonavuser")
        request = _make_request("", user=regular)
        html = _render_tag("{% desktop_nav %}", request)
        self.assertIn("nav--desktop", html)
        self.assertIn("Machines", html)
        self.assertIn("Problems", html)
        self.assertIn("Logs", html)
        self.assertNotIn("Parts", html)
        self.assertNotIn("Docs", html)


@tag("views")
class MobilePriorityBarRenderTests(TestCase):
    """Rendered HTML assertions for {% mobile_priority_bar %}."""

    def setUp(self):
        self.user = create_maintainer_user(username="mobiletest")

    def test_active_item_has_active_class(self):
        """Active item gets nav-priority__item--active."""
        request = _make_request("log-list", user=self.user)
        html = _render_tag("{% mobile_priority_bar %}", request)
        self.assertIn("nav-priority__item--active", html)

    def test_docs_not_in_bar(self):
        """Docs should not appear in the mobile priority bar."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_priority_bar %}", request)
        self.assertNotIn(">Docs<", html)

    def test_four_items_in_bar(self):
        """Machines, Problems, Logs, Parts appear in mobile bar."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_priority_bar %}", request)
        for label in ("Machines", "Problems", "Logs", "Parts"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_logs_has_extra_class(self):
        """Logs item has the --logs responsive visibility class."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_priority_bar %}", request)
        self.assertIn("nav-priority__item--logs", html)

    def test_parts_has_extra_class(self):
        """Parts item has the --parts responsive visibility class."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_priority_bar %}", request)
        self.assertIn("nav-priority__item--parts", html)


@tag("views")
class MobileHamburgerRenderTests(TestCase):
    """Rendered HTML assertions for {% mobile_hamburger %}."""

    def setUp(self):
        self.user = create_maintainer_user(username="hamburgertest")

    def test_all_nav_items_present(self):
        """All 5 nav items render in hamburger dropdown."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        for label in ("Machines", "Problems", "Logs", "Parts", "Docs"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_active_item_has_selected_class(self):
        """Active item gets dropdown__item--selected."""
        request = _make_request("wiki-home", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("dropdown__item--selected", html)

    def test_active_item_has_aria_current(self):
        """Active item gets aria-current='page'."""
        request = _make_request("wiki-home", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn('aria-current="page"', html)

    def test_hamburger_button_active_for_wiki(self):
        """Hamburger button lights up when on wiki page."""
        request = _make_request("wiki-home", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("nav-priority__menu-btn--active", html)

    def test_hamburger_button_active_for_profile(self):
        """Hamburger button lights up when on profile page."""
        request = _make_request("profile", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("nav-priority__menu-btn--active", html)

    def test_hamburger_button_active_for_logs_class(self):
        """Hamburger has --active-for-logs when on log routes."""
        request = _make_request("log-list", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("nav-priority__menu-btn--active-for-logs", html)

    def test_hamburger_button_active_for_parts_class(self):
        """Hamburger has --active-for-parts when on part routes."""
        request = _make_request("part-request-list", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("nav-priority__menu-btn--active-for-parts", html)

    def test_admin_section_for_superuser(self):
        """Superuser sees admin section in hamburger."""
        superuser = create_superuser(username="hamburgeradmin")
        request = _make_request("", user=superuser)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("Wall Display", html)
        self.assertIn("Django Admin", html)

    def test_no_admin_for_regular_maintainer(self):
        """Regular maintainer does not see admin section."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertNotIn("Wall Display", html)

    def test_logout_form_has_csrf(self):
        """Logout form has a CSRF token hidden input."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_account_section_present(self):
        """Account link and logout button render."""
        request = _make_request("", user=self.user)
        html = _render_tag("{% mobile_hamburger %}", request)
        self.assertIn("Account", html)
        self.assertIn("Logout", html)


@tag("views")
class UserDropdownRenderTests(TestCase):
    """Rendered HTML assertions for {% user_dropdown %}."""

    def test_authenticated_user_sees_avatar(self):
        """Authenticated user sees avatar button."""
        user = create_maintainer_user(username="avatartest")
        request = _make_request("", user=user)
        html = _render_tag("{% user_dropdown %}", request)
        self.assertIn("avatar", html)
        self.assertIn("Account menu", html)

    def test_avatar_initials_full_name(self):
        """User with first and last name shows initials."""
        user = create_maintainer_user(username="initialstest", first_name="John", last_name="Doe")
        request = _make_request("", user=user)
        html = _render_tag("{% user_dropdown %}", request)
        self.assertIn("JD", html)

    def test_unauthenticated_user_sees_login(self):
        """Anonymous user sees login link instead of avatar."""
        from django.contrib.auth.models import AnonymousUser

        request = _make_request("", user=AnonymousUser())
        html = _render_tag("{% user_dropdown %}", request)
        self.assertIn("Login", html)
        self.assertNotIn("avatar", html)

    def test_logout_form_has_csrf(self):
        """Logout form in user dropdown has CSRF token."""
        user = create_maintainer_user(username="csrftest")
        request = _make_request("", user=user)
        html = _render_tag("{% user_dropdown %}", request)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_mobile_hidden_for_maintainer(self):
        """Maintainer's avatar dropdown is hidden on mobile."""
        user = create_maintainer_user(username="mobilehidetest")
        request = _make_request("", user=user)
        html = _render_tag("{% user_dropdown %}", request)
        self.assertIn("avatar-dropdown--mobile-hidden", html)
