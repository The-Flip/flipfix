from django.apps import AppConfig


class DiscordConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.discord"

    def ready(self):
        from the_flip.apps.discord import signals  # noqa: F401
