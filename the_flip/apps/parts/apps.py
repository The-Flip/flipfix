"""Parts app configuration."""

from django.apps import AppConfig


class PartsConfig(AppConfig):
    """Configuration for the parts app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.parts"
    verbose_name = "Parts Management"

    def ready(self):
        """Import signals when the app is ready."""
        from the_flip.apps.parts import signals  # noqa: F401
