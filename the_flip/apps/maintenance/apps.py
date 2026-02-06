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

        from . import signals

        del signals  # imported for side effects (signal registration)

        self._register_link_types()

    @staticmethod
    def _register_link_types():
        from the_flip.apps.core.markdown_links import LinkType, link_preview, register

        def _problem_label(obj):
            label = f"Problem #{obj.pk}"
            if obj.description:
                label += f": {link_preview(obj.description)}"
            return label

        def _log_label(obj):
            label = f"Log #{obj.pk}"
            if obj.text:
                label += f": {link_preview(obj.text)}"
            return label

        def _serialize_problem(obj):
            return {
                "label": f"#{obj.pk}: {obj.machine.short_display_name} - {(obj.description or '')[:50]}",
                "ref": str(obj.pk),
            }

        def _serialize_log(obj):
            return {
                "label": f"#{obj.pk}: {obj.machine.short_display_name} - {(obj.text or '')[:50]}",
                "ref": str(obj.pk),
            }

        register(
            LinkType(
                name="problem",
                model_path="maintenance.ProblemReport",
                label="Problem",
                description="Link to a problem report",
                url_name="problem-report-detail",
                get_label=_problem_label,
                autocomplete_search_fields=("description", "id"),
                autocomplete_ordering=("-created_at",),
                autocomplete_select_related=("machine",),
                autocomplete_serialize=_serialize_problem,
                sort_order=30,
            )
        )

        register(
            LinkType(
                name="log",
                model_path="maintenance.LogEntry",
                label="Log",
                description="Link to a log entry",
                url_name="log-detail",
                get_label=_log_label,
                autocomplete_search_fields=("text", "id"),
                autocomplete_ordering=("-created_at",),
                autocomplete_select_related=("machine",),
                autocomplete_serialize=_serialize_log,
                sort_order=40,
            )
        )
