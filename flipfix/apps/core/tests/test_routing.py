"""Tests for the routing module (path wrapper, public access, superuser gating).

Uses a minimal test URLconf with dummy views wired through our path().
"""

from __future__ import annotations

from types import MappingProxyType

from constance.test import override_config
from django.http import HttpResponse
from django.test import override_settings, tag

from flipfix.apps.core.routing import get_public_url_names, get_registered_routes, path
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_maintainer_user,
    create_superuser,
    create_user,
)

# ---------------------------------------------------------------------------
# Dummy views for test URLconf
# ---------------------------------------------------------------------------


def _dummy_view(request):
    """Minimal view that returns 200 OK."""
    return HttpResponse("ok")


# ---------------------------------------------------------------------------
# Test URLconf — referenced by ROOT_URLCONF override
# ---------------------------------------------------------------------------

urlpatterns = [
    path("public/", _dummy_view, name="test-public", access="public"),
    path("always-public/", _dummy_view, name="test-always-public", access="always_public"),
    path("superuser/", _dummy_view, name="test-superuser", access="superuser"),
    path("default/", _dummy_view, name="test-default"),
    path("login/", _dummy_view, name="login"),  # Required by redirect_to_login
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_URLCONF = "flipfix.apps.core.tests.test_routing"


# ---------------------------------------------------------------------------
# Public access routing tests
# ---------------------------------------------------------------------------


@tag("views")
@override_settings(ROOT_URLCONF=_TEST_URLCONF)
class PublicAccessRoutingTests(AccessControlTestCase):
    """Tests for access='public' routing behavior."""

    def setUp(self):
        super().setUp()
        self.maintainer = create_maintainer_user()
        self.regular_user = create_user()

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_anonymous_get_public_route_toggle_on_returns_200(self):
        """Anonymous GET to access='public' route returns 200 when toggle is on."""
        response = self.client.get("/public/")
        self.assertEqual(response.status_code, 200)

    @override_config(PUBLIC_ACCESS_ENABLED=False)
    def test_anonymous_get_public_route_toggle_off_redirects_to_login(self):
        """Anonymous GET to access='public' route redirects to login when toggle is off."""
        response = self.client.get("/public/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_anonymous_post_public_route_returns_405(self):
        """Anonymous POST to access='public' route returns 405 (read-only for guests)."""
        response = self.client.post("/public/")
        self.assertEqual(response.status_code, 405)

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_authenticated_get_public_route_returns_200(self):
        """Authenticated GET to access='public' route returns 200."""
        self.client.force_login(self.maintainer)
        response = self.client.get("/public/")
        self.assertEqual(response.status_code, 200)

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_public_response_has_cache_control(self):
        """Public (guest) response has Cache-Control: public, max-age=300."""
        response = self.client.get("/public/")
        cc = response.get("Cache-Control", "")
        self.assertIn("public", cc)
        self.assertIn("max-age=300", cc)

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_authenticated_response_no_public_cache(self):
        """Authenticated response does NOT have Cache-Control: public."""
        self.client.force_login(self.maintainer)
        response = self.client.get("/public/")
        cc = response.get("Cache-Control", "")
        self.assertNotIn("public", cc)


# ---------------------------------------------------------------------------
# Always-public routing tests
# ---------------------------------------------------------------------------


@tag("views")
@override_settings(ROOT_URLCONF=_TEST_URLCONF)
class AlwaysPublicRoutingTests(AccessControlTestCase):
    """Tests for access='always_public' routing behavior."""

    def test_anonymous_get_returns_200(self):
        """Anonymous GET to access='always_public' route returns 200."""
        response = self.client.get("/always-public/")
        self.assertEqual(response.status_code, 200)

    def test_anonymous_post_allowed(self):
        """Anonymous POST to access='always_public' route is allowed (unlike 'public')."""
        response = self.client.post("/always-public/")
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Superuser routing tests
# ---------------------------------------------------------------------------


@tag("views")
@override_settings(ROOT_URLCONF=_TEST_URLCONF)
class SuperuserRoutingTests(AccessControlTestCase):
    """Tests for access='superuser' routing behavior."""

    def setUp(self):
        super().setUp()
        self.maintainer = create_maintainer_user()
        self.superuser = create_superuser()

    def test_non_superuser_gets_403(self):
        """Non-superuser accessing access='superuser' route gets 403."""
        self.client.force_login(self.maintainer)
        response = self.client.get("/superuser/")
        self.assertEqual(response.status_code, 403)

    def test_superuser_gets_200(self):
        """Superuser accessing access='superuser' route gets 200."""
        self.client.force_login(self.superuser)
        response = self.client.get("/superuser/")
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# URL name registry tests
# ---------------------------------------------------------------------------


@tag("views")
class PublicUrlNameRegistryTests(AccessControlTestCase):
    """Tests for get_public_url_names() registry."""

    def test_public_route_name_registered(self):
        """access='public' routes are registered in get_public_url_names()."""
        names = get_public_url_names()
        self.assertIn("test-public", names)

    def test_default_route_not_registered(self):
        """Default routes are NOT registered in get_public_url_names()."""
        names = get_public_url_names()
        self.assertNotIn("test-default", names)

    def test_superuser_route_not_registered(self):
        """access='superuser' routes are NOT registered in get_public_url_names()."""
        names = get_public_url_names()
        self.assertNotIn("test-superuser", names)

    def test_always_public_route_not_registered(self):
        """access='always_public' routes are NOT registered in get_public_url_names()."""
        names = get_public_url_names()
        self.assertNotIn("test-always-public", names)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@tag("views")
class PathValidationTests(AccessControlTestCase):
    """Tests for path() argument validation."""

    def test_invalid_access_raises_value_error(self):
        """path() with invalid access level raises ValueError."""
        with self.assertRaises(ValueError):
            path("bad/", _dummy_view, name="test-bad", access="invalid")


# ---------------------------------------------------------------------------
# Route access registry
# ---------------------------------------------------------------------------


@tag("views")
class RouteAccessRegistryTests(AccessControlTestCase):
    """get_registered_routes() exposes each route's declared access level.

    The mobile parity audit uses this to enumerate every page and pick a user
    with the right permissions for it, so the registry must stay complete.
    """

    def test_every_access_level_is_recorded(self):
        routes = get_registered_routes()
        self.assertEqual(routes["test-public"], "public")
        self.assertEqual(routes["test-always-public"], "always_public")
        self.assertEqual(routes["test-superuser"], "superuser")

    def test_default_route_records_none(self):
        """No access= means the default: a logged-in maintainer."""
        self.assertIsNone(get_registered_routes()["test-default"])

    def test_registry_is_read_only(self):
        """Callers get a proxy, so nobody can reshape the routing table by accident."""
        self.assertIsInstance(get_registered_routes(), MappingProxyType)

    def test_real_urlconf_routes_are_registered(self):
        """The project's own URLs register too, not just this test URLconf."""
        routes = get_registered_routes()
        self.assertIn("home", routes)
        self.assertEqual(routes["healthz"], "always_public")
