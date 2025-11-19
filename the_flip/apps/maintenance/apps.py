from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.maintenance"
    verbose_name = "Maintenance"
