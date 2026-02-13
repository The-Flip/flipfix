from django.apps import AppConfig


class DiscordConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.discord"

    def ready(self):
        from the_flip.apps.discord.bot_handlers import discover as discover_bot_handlers
        from the_flip.apps.discord.webhook_handlers import (
            connect_signals,
        )
        from the_flip.apps.discord.webhook_handlers import (
            discover as discover_webhook_handlers,
        )

        discover_bot_handlers()
        discover_webhook_handlers()

        connect_signals()
