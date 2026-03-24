"""Tests for OAuth2/OIDC SSO provider."""

from __future__ import annotations

import hashlib
import secrets
from base64 import urlsafe_b64encode
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings, tag

from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_app_capability,
    create_maintainer_user,
    create_oauth_application,
    create_superuser,
    create_user,
    grant_capability,
    grant_capability_to_group,
)
from flipfix.apps.oauth.models import (
    AppCapability,
    AppCapabilityGrant,
    AppCapabilityGroupGrant,
)


def _generate_test_rsa_key() -> str:
    """Generate an RSA private key PEM for test OIDC signing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


# Generate once per module for test performance
_TEST_RSA_KEY = _generate_test_rsa_key()

_OIDC_SETTINGS = {
    "OIDC_ENABLED": True,
    "OIDC_ISS_ENDPOINT": "http://testserver",
    "OIDC_RSA_PRIVATE_KEY": _TEST_RSA_KEY,
    "SCOPES": {
        "openid": "OpenID Connect",
        "profile": "User profile",
        "email": "Email address",
        "capabilities": "App-specific capabilities",
    },
    "OAUTH2_VALIDATOR_CLASS": "flipfix.apps.oauth.validators.FlipFixOAuth2Validator",
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 2592000,
    "ROTATE_REFRESH_TOKEN": True,
    "PKCE_REQUIRED": True,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["http", "https"],
}


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# =============================================================================
# Model Tests
# =============================================================================


@tag("models")
class AppCapabilityModelTests(TestCase):
    def test_str_representation(self):
        app = create_oauth_application(name="Juice")
        cap = create_app_capability(app=app, slug="control_power", name="Control Machine Power")
        self.assertEqual(str(cap), "Juice: Control Machine Power")

    def test_unique_slug_per_app(self):
        from django.db import IntegrityError

        app = create_oauth_application()
        create_app_capability(app=app, slug="power")
        with self.assertRaises(IntegrityError):
            create_app_capability(app=app, slug="power")

    def test_same_slug_different_apps(self):
        app1 = create_oauth_application(name="App 1")
        app2 = create_oauth_application(name="App 2")
        cap1 = create_app_capability(app=app1, slug="view")
        cap2 = create_app_capability(app=app2, slug="view")
        self.assertNotEqual(cap1.pk, cap2.pk)

    def test_cascade_delete_with_application(self):
        app = create_oauth_application()
        create_app_capability(app=app, slug="power")
        app.delete()
        self.assertEqual(AppCapability.objects.count(), 0)


@tag("models")
class AppCapabilityGrantModelTests(TestCase):
    def test_str_representation(self):
        user = create_user(username="alice")
        app = create_oauth_application(name="Juice")
        cap = create_app_capability(app=app, slug="power", name="Power Control")
        g = grant_capability(user, cap)
        self.assertEqual(str(g), "alice -> Juice: Power Control")

    def test_unique_grant_per_user(self):
        from django.db import IntegrityError

        user = create_user()
        cap = create_app_capability()
        grant_capability(user, cap)
        with self.assertRaises(IntegrityError):
            grant_capability(user, cap)

    def test_cascade_delete_with_capability(self):
        user = create_user()
        cap = create_app_capability()
        grant_capability(user, cap)
        cap.delete()
        self.assertEqual(AppCapabilityGrant.objects.count(), 0)

    def test_granted_by_set_null_on_delete(self):
        granter = create_superuser()
        user = create_user()
        cap = create_app_capability()
        g = grant_capability(user, cap, granted_by=granter)
        granter.delete()
        g.refresh_from_db()
        self.assertIsNone(g.granted_by)


@tag("models")
class AppCapabilityGroupGrantModelTests(TestCase):
    def test_str_representation(self):
        group = Group.objects.create(name="Testers")
        app = create_oauth_application(name="Juice")
        cap = create_app_capability(app=app, slug="power", name="Power Control")
        g = grant_capability_to_group(group, cap)
        self.assertEqual(str(g), "Testers -> Juice: Power Control")

    def test_unique_grant_per_group(self):
        from django.db import IntegrityError

        group = Group.objects.create(name="Testers")
        cap = create_app_capability()
        grant_capability_to_group(group, cap)
        with self.assertRaises(IntegrityError):
            grant_capability_to_group(group, cap)

    def test_cascade_delete_with_capability(self):
        group = Group.objects.create(name="Testers")
        cap = create_app_capability()
        grant_capability_to_group(group, cap)
        cap.delete()
        self.assertEqual(AppCapabilityGroupGrant.objects.count(), 0)

    def test_cascade_delete_with_group(self):
        group = Group.objects.create(name="Testers")
        cap = create_app_capability()
        grant_capability_to_group(group, cap)
        group.delete()
        self.assertEqual(AppCapabilityGroupGrant.objects.count(), 0)

    def test_granted_by_set_null_on_delete(self):
        granter = create_superuser()
        group = Group.objects.create(name="Testers")
        cap = create_app_capability()
        g = grant_capability_to_group(group, cap, granted_by=granter)
        granter.delete()
        g.refresh_from_db()
        self.assertIsNone(g.granted_by)


# =============================================================================
# OAuth2 Flow Tests
# =============================================================================


@tag("views")
@override_settings(OAUTH2_PROVIDER=_OIDC_SETTINGS)
class OAuthAuthorizationFlowTests(AccessControlTestCase):
    """Test the OAuth2 Authorization Code + PKCE flow end-to-end."""

    def setUp(self):
        super().setUp()
        self.app = create_oauth_application(name="Juice")
        self.user = create_maintainer_user(username="alice", first_name="Alice", last_name="Smith")
        self.cap = create_app_capability(app=self.app, slug="control_power", name="Control Power")
        grant_capability(self.user, self.cap)

    def _authorize(self, user, scopes="openid profile capabilities"):
        """Run the authorization step and return the auth code."""
        self.client.force_login(user)
        verifier, challenge = _pkce_pair()

        response = self.client.get(
            "/oauth/authorize/",
            {
                "response_type": "code",
                "client_id": self.app.client_id,
                "redirect_uri": "http://testserver/callback",
                "scope": scopes,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        # skip_authorization=True means immediate redirect (SSO)
        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.url)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.netloc, "testserver")
        self.assertEqual(parsed.path, "/callback")

        qs = parse_qs(parsed.query)
        self.assertIn("code", qs)
        return qs["code"][0], verifier

    def _exchange_token(self, code, verifier):
        """Exchange an authorization code for tokens."""
        response = self.client.post(
            "/oauth/token/",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://testserver/callback",
                "client_id": self.app.client_id,
                "client_secret": self.app.plain_client_secret,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertIn("id_token", data)
        return data

    def test_full_authorization_code_flow(self):
        """Complete auth code + PKCE flow: authorize -> token -> userinfo."""
        code, verifier = self._authorize(self.user)
        tokens = self._exchange_token(code, verifier)

        # Call userinfo with the access token
        response = self.client.get(
            "/oauth/userinfo/",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 200)
        claims = response.json()
        self.assertEqual(claims["sub"], str(self.user.pk))
        self.assertEqual(claims["preferred_username"], "alice")
        self.assertEqual(claims["name"], "Alice Smith")
        self.assertTrue(claims["is_maintainer"])
        self.assertEqual(claims["https://flipfix.theflip.museum/capabilities"], ["control_power"])

    def test_sso_silent_redirect(self):
        """Authenticated user gets immediate redirect (no login form, no consent)."""
        self.client.force_login(self.user)
        _, challenge = _pkce_pair()

        response = self.client.get(
            "/oauth/authorize/",
            {
                "response_type": "code",
                "client_id": self.app.client_id,
                "redirect_uri": "http://testserver/callback",
                "scope": "openid",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        # Should be a redirect directly to callback, not to a login or consent page
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("http://testserver/callback"))

    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated user is redirected to login."""
        response = self.client.get("/oauth/authorize/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_without_capability_gets_empty_list(self):
        """User without any capability grants gets empty capabilities list."""
        user_no_caps = create_maintainer_user(username="bob")
        code, verifier = self._authorize(user_no_caps)
        tokens = self._exchange_token(code, verifier)

        response = self.client.get(
            "/oauth/userinfo/",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
        )
        claims = response.json()
        self.assertEqual(claims["https://flipfix.theflip.museum/capabilities"], [])

    def test_token_refresh(self):
        """Refresh token can be used to get a new access token."""
        code, verifier = self._authorize(self.user)
        tokens = self._exchange_token(code, verifier)

        response = self.client.post(
            "/oauth/token/",
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": self.app.client_id,
                "client_secret": self.app.plain_client_secret,
            },
        )
        self.assertEqual(response.status_code, 200)
        new_tokens = response.json()
        self.assertIn("access_token", new_tokens)
        self.assertNotEqual(new_tokens["access_token"], tokens["access_token"])

    def test_token_revocation(self):
        """Access token can be revoked."""
        code, verifier = self._authorize(self.user)
        tokens = self._exchange_token(code, verifier)

        response = self.client.post(
            "/oauth/revoke/",
            {
                "token": tokens["access_token"],
                "client_id": self.app.client_id,
                "client_secret": self.app.plain_client_secret,
            },
        )
        self.assertEqual(response.status_code, 200)

        # Token should no longer work
        response = self.client.get(
            "/oauth/userinfo/",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
        )
        self.assertNotEqual(response.status_code, 200)


# =============================================================================
# Discovery & JWKS Tests
# =============================================================================


@tag("views")
@override_settings(OAUTH2_PROVIDER=_OIDC_SETTINGS)
class OIDCDiscoveryTests(TestCase):
    def test_discovery_endpoint(self):
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("authorization_endpoint", data)
        self.assertIn("token_endpoint", data)
        self.assertIn("userinfo_endpoint", data)
        self.assertIn("jwks_uri", data)
        self.assertIn("openid", data["scopes_supported"])
        self.assertIn("capabilities", data["scopes_supported"])
        # Verify URLs use our custom names, not DOT's namespaced names
        self.assertIn("/oauth/authorize/", data["authorization_endpoint"])
        self.assertIn("/oauth/token/", data["token_endpoint"])
        self.assertIn("/oauth/userinfo/", data["userinfo_endpoint"])

    @override_settings(
        ALLOWED_HOSTS=["other.example.com", "testserver"],
        OAUTH2_PROVIDER=_OIDC_SETTINGS,
    )
    def test_discovery_endpoints_use_issuer_not_request_host(self):
        """Discovery endpoints are anchored to OIDC_ISS_ENDPOINT, not the request Host."""
        response = self.client.get(
            "/.well-known/openid-configuration",
            HTTP_HOST="other.example.com",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # All endpoints should use the configured issuer (http://testserver), not the request host
        self.assertTrue(data["authorization_endpoint"].startswith("http://testserver/"))
        self.assertTrue(data["token_endpoint"].startswith("http://testserver/"))
        self.assertTrue(data["userinfo_endpoint"].startswith("http://testserver/"))
        self.assertTrue(data["jwks_uri"].startswith("http://testserver/"))
        self.assertNotIn("other.example.com", data["authorization_endpoint"])

    def test_jwks_endpoint(self):
        response = self.client.get("/.well-known/jwks.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("keys", data)
        self.assertGreater(len(data["keys"]), 0)
        self.assertEqual(data["keys"][0]["alg"], "RS256")


# =============================================================================
# Access Control Tests
# =============================================================================


@tag("views")
class OAuthAccessControlTests(AccessControlTestCase):
    def test_token_endpoint_is_public(self):
        """Token endpoint accepts unauthenticated requests (returns 400, not 302)."""
        response = self.client.post("/oauth/token/")
        # Bad request (missing params), but not a login redirect
        self.assertIn(response.status_code, (400, 401))

    def test_userinfo_without_bearer_returns_401(self):
        """Userinfo without Bearer token returns 401, not login redirect."""
        response = self.client.get("/oauth/userinfo/")
        self.assertEqual(response.status_code, 401)

    def test_revoke_endpoint_is_public(self):
        """Revoke endpoint accepts unauthenticated requests."""
        response = self.client.post("/oauth/revoke/")
        # Bad request (missing params), but not a login redirect
        self.assertIn(response.status_code, (200, 400, 401))

    @override_settings(OAUTH2_PROVIDER=_OIDC_SETTINGS)
    def test_discovery_is_public(self):
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)

    @override_settings(OAUTH2_PROVIDER=_OIDC_SETTINGS)
    def test_jwks_is_public(self):
        response = self.client.get("/.well-known/jwks.json")
        self.assertEqual(response.status_code, 200)


# =============================================================================
# Group Capability Tests
# =============================================================================


@tag("views")
@override_settings(OAUTH2_PROVIDER=_OIDC_SETTINGS)
class OAuthGroupCapabilityTests(AccessControlTestCase):
    """Test that group-based capability grants appear in OIDC claims."""

    def setUp(self):
        super().setUp()
        self.app = create_oauth_application(name="Juice")
        self.user = create_maintainer_user(username="alice")
        self.group = Group.objects.get(name="Maintainers")
        self.cap = create_app_capability(app=self.app, slug="control_power", name="Control Power")

    def _get_capabilities(self, user):
        """Run the full OAuth flow and return the capabilities claim."""
        self.client.force_login(user)
        verifier, challenge = _pkce_pair()
        response = self.client.get(
            "/oauth/authorize/",
            {
                "response_type": "code",
                "client_id": self.app.client_id,
                "redirect_uri": "http://testserver/callback",
                "scope": "openid capabilities",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        self.assertEqual(response.status_code, 302)
        code = parse_qs(urlparse(response.url).query)["code"][0]

        token_response = self.client.post(
            "/oauth/token/",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://testserver/callback",
                "client_id": self.app.client_id,
                "client_secret": self.app.plain_client_secret,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(token_response.status_code, 200)
        access_token = token_response.json()["access_token"]

        userinfo_response = self.client.get(
            "/oauth/userinfo/",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(userinfo_response.status_code, 200)
        return userinfo_response.json()["https://flipfix.theflip.museum/capabilities"]

    def test_group_grant_appears_in_capabilities(self):
        grant_capability_to_group(self.group, self.cap)
        caps = self._get_capabilities(self.user)
        self.assertEqual(caps, ["control_power"])

    def test_direct_and_group_grant_deduplicated(self):
        grant_capability(self.user, self.cap)
        grant_capability_to_group(self.group, self.cap)
        caps = self._get_capabilities(self.user)
        self.assertEqual(caps, ["control_power"])

    def test_group_grant_scoped_to_app(self):
        """Group grant on one app doesn't leak to another."""
        grant_capability_to_group(self.group, self.cap)
        other_app = create_oauth_application(name="Other")
        other_cap = create_app_capability(app=other_app, slug="other_cap", name="Other")
        grant_capability_to_group(self.group, other_cap)
        caps = self._get_capabilities(self.user)
        self.assertEqual(caps, ["control_power"])

    def test_user_not_in_group_doesnt_get_group_capability(self):
        grant_capability_to_group(self.group, self.cap)
        # Create a maintainer user in a different group
        other_user = create_maintainer_user(username="bob")
        other_user.groups.clear()
        other_group = Group.objects.create(name="Other Group")
        other_user.groups.add(other_group)
        caps = self._get_capabilities(other_user)
        self.assertEqual(caps, [])


# =============================================================================
# Admin Tests
# =============================================================================


@tag("views")
class OAuthAdminTests(AccessControlTestCase):
    def test_superuser_can_access_capability_admin(self):
        superuser = create_superuser()
        self.client.force_login(superuser)
        response = self.client.get("/admin/oauth/appcapability/")
        self.assertEqual(response.status_code, 200)

    def test_non_staff_redirected_from_capability_admin(self):
        """Non-staff user is redirected to admin login."""
        maintainer = create_maintainer_user()
        self.client.force_login(maintainer)
        response = self.client.get("/admin/oauth/appcapability/")
        self.assertEqual(response.status_code, 302)

    def test_staff_non_superuser_denied_capability_admin(self):
        """Staff user without superuser gets 403 from our permission checks."""
        staff_user = create_user(is_staff=True)
        self.client.force_login(staff_user)
        response = self.client.get("/admin/oauth/appcapability/")
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_group_grant_admin(self):
        superuser = create_superuser()
        self.client.force_login(superuser)
        response = self.client.get("/admin/oauth/appcapabilitygroupgrant/")
        self.assertEqual(response.status_code, 200)
