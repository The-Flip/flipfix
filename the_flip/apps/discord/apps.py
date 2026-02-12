from django.apps import AppConfig


class DiscordConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.discord"

    def ready(self):
        # Import handler modules to trigger registration via register() calls
        from the_flip.apps.discord.bot_handlers import log_entry as _bot_log_entry  # noqa: F401
        from the_flip.apps.discord.bot_handlers import (
            part_request as _bot_part_request,  # noqa: F401
        )
        from the_flip.apps.discord.bot_handlers import (
            part_request_update as _bot_part_request_update,  # noqa: F401
        )
        from the_flip.apps.discord.bot_handlers import (
            problem_report as _bot_problem_report,  # noqa: F401
        )
        from the_flip.apps.discord.webhook_handlers import connect_signals
        from the_flip.apps.discord.webhook_handlers import log_entry as _wh_log_entry  # noqa: F401
        from the_flip.apps.discord.webhook_handlers import (
            part_request as _wh_part_request,  # noqa: F401
        )
        from the_flip.apps.discord.webhook_handlers import (
            part_request_update as _wh_part_request_update,  # noqa: F401
        )
        from the_flip.apps.discord.webhook_handlers import (
            problem_report as _wh_problem_report,  # noqa: F401
        )

        connect_signals()
