from django.apps import AppConfig


class OAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flipfix.apps.oauth"
    verbose_name = "OAuth2 Provider"
