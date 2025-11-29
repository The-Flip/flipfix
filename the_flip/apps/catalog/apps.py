from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.catalog"
    verbose_name = "Catalog"

    def ready(self):
        from the_flip.apps.catalog import signals  # noqa: F401
