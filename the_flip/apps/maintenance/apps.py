from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        """Register HEIF opener so Pillow can read HEIC/HEIF uploads."""
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:  # pragma: no cover - best-effort hook
            import logging

            logging.getLogger(__name__).warning("HEIF support unavailable; HEIC decode may fail.")
