from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flipfix.apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        from flipfix.apps.core.models import register_media_model

        from . import signals  # noqa: F401
        from .models import MaintainerMedia

        register_media_model(MaintainerMedia)
