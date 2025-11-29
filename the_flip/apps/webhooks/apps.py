from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.webhooks"

    def ready(self):
        from the_flip.apps.webhooks import signals  # noqa: F401
