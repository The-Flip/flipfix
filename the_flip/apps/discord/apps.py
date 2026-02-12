import importlib

from django.apps import AppConfig


class DiscordConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.discord"

    def ready(self):
        # Import handler modules to trigger registration via register() calls
        importlib.import_module("the_flip.apps.discord.bot_handlers.log_entry")
        importlib.import_module("the_flip.apps.discord.bot_handlers.part_request")
        importlib.import_module("the_flip.apps.discord.bot_handlers.part_request_update")
        importlib.import_module("the_flip.apps.discord.bot_handlers.problem_report")
        importlib.import_module("the_flip.apps.discord.webhook_handlers.log_entry")
        importlib.import_module("the_flip.apps.discord.webhook_handlers.part_request")
        importlib.import_module("the_flip.apps.discord.webhook_handlers.part_request_update")
        importlib.import_module("the_flip.apps.discord.webhook_handlers.problem_report")

        from the_flip.apps.discord.webhook_handlers import connect_signals

        connect_signals()
