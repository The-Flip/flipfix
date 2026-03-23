"""Custom OAuth2 validator for FlipFix OIDC claims."""

from oauth2_provider.oauth2_validators import OAuth2Validator

from flipfix.apps.oauth.models import AppCapabilityGrant


class FlipFixOAuth2Validator(OAuth2Validator):
    oidc_claim_scope = {
        **OAuth2Validator.oidc_claim_scope,
        "preferred_username": "profile",
        "given_name": "profile",
        "family_name": "profile",
        "is_maintainer": "profile",
        "email": "email",
        "email_verified": "email",
        "https://flipfix.theflip.museum/capabilities": "capabilities",
    }

    def get_additional_claims(self, request):
        user = request.user
        claims = {
            "preferred_username": user.username,
            "name": user.get_full_name() or user.username,
            "given_name": user.first_name,
            "family_name": user.last_name,
            "is_maintainer": user.has_perm("accounts.can_access_maintainer_portal"),
            "email": user.email,
            "email_verified": bool(user.email),
        }

        capability_slugs = list(
            AppCapabilityGrant.objects.filter(
                user=user,
                capability__app=request.client,
            ).values_list("capability__slug", flat=True)
        )
        claims["https://flipfix.theflip.museum/capabilities"] = capability_slugs

        return claims

    def get_discovery_claims(self, request):
        return [
            "sub",
            "preferred_username",
            "name",
            "given_name",
            "family_name",
            "email",
            "email_verified",
            "is_maintainer",
            "https://flipfix.theflip.museum/capabilities",
        ]
