"""Thin wrappers around django-oauth-toolkit views.

DOT's views handle their own authentication (LoginRequiredMixin for authorize,
Bearer token for userinfo, csrf_exempt for token). These wrappers exist so we
can wire them into the project's route-level access system in urls.py.

The ConnectDiscoveryInfoView is overridden to use this project's URL names
instead of DOT's namespaced names (we don't use DOT's include() pattern).
"""

from urllib.parse import urljoin

from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from oauth2_provider.compat import login_not_required
from oauth2_provider.models import AbstractGrant
from oauth2_provider.settings import oauth2_settings
from oauth2_provider.views import AuthorizationView as DOTAuthorizationView
from oauth2_provider.views import RevokeTokenView as DOTRevokeTokenView
from oauth2_provider.views import TokenView as DOTTokenView
from oauth2_provider.views.mixins import OIDCOnlyMixin
from oauth2_provider.views.oidc import JwksInfoView as DOTJwksView
from oauth2_provider.views.oidc import UserInfoView as DOTUserInfoView


class AuthorizationView(DOTAuthorizationView):
    pass


class TokenView(DOTTokenView):
    pass


class RevokeTokenView(DOTRevokeTokenView):
    pass


class UserInfoView(DOTUserInfoView):
    pass


@method_decorator(login_not_required, name="dispatch")
class ConnectDiscoveryInfoView(OIDCOnlyMixin, View):
    """OIDC discovery endpoint using this project's URL names."""

    def get(self, request, *args, **kwargs):
        issuer_url = oauth2_settings.OIDC_ISS_ENDPOINT or oauth2_settings.oidc_issuer(request)
        issuer_base = issuer_url.rstrip("/") + "/"

        def _endpoint(url_name: str) -> str:
            """Build an endpoint URL anchored to the issuer, not the request host."""
            return urljoin(issuer_base, reverse(url_name).lstrip("/"))

        from oauth2_provider.models import get_application_model

        app_model = get_application_model()
        signing_algorithms = [app_model.HS256_ALGORITHM]
        if oauth2_settings.OIDC_RSA_PRIVATE_KEY:
            signing_algorithms = [app_model.RS256_ALGORITHM, app_model.HS256_ALGORITHM]

        validator_class = oauth2_settings.OAUTH2_VALIDATOR_CLASS
        validator = validator_class()
        oidc_claims = list(set(validator.get_discovery_claims(request)))
        scopes_class = oauth2_settings.SCOPES_BACKEND_CLASS
        scopes = scopes_class()

        data = {
            "issuer": issuer_url,
            "authorization_endpoint": _endpoint("oauth2-authorize"),
            "token_endpoint": _endpoint("oauth2-token"),
            "userinfo_endpoint": _endpoint("oauth2-userinfo"),
            "jwks_uri": _endpoint("oauth2-jwks"),
            "scopes_supported": list(scopes.get_available_scopes()),
            "response_types_supported": oauth2_settings.OIDC_RESPONSE_TYPES_SUPPORTED,
            "subject_types_supported": oauth2_settings.OIDC_SUBJECT_TYPES_SUPPORTED,
            "id_token_signing_alg_values_supported": signing_algorithms,
            "token_endpoint_auth_methods_supported": (
                oauth2_settings.OIDC_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED
            ),
            "code_challenge_methods_supported": [
                key for key, _ in AbstractGrant.CODE_CHALLENGE_METHODS
            ],
            "claims_supported": oidc_claims,
        }
        response = JsonResponse(data)
        response["Access-Control-Allow-Origin"] = "*"
        return response


class JwksInfoView(DOTJwksView):
    pass
