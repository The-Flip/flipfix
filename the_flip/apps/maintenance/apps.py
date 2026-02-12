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

        from the_flip.apps.core.models import register_reference_cleanup

        from .models import LogEntry, ProblemReport

        register_reference_cleanup(ProblemReport, LogEntry)

        from . import signals  # noqa: F401 — registers @receiver handlers

        self._register_feed_sources()
        self._register_link_types()
        self._register_media_models()

    @staticmethod
    def _register_feed_sources():
        from django.db.models import Prefetch

        from the_flip.apps.core.feed import FeedEntrySource, register_feed_source

        from .models import LogEntry, ProblemReport

        def _log_entry_queryset():
            return LogEntry.objects.select_related("problem_report").prefetch_related(
                "maintainers__user", "media"
            )

        def _problem_report_queryset():
            latest_log_prefetch = Prefetch(
                "log_entries",
                queryset=LogEntry.objects.order_by("-occurred_at"),
                to_attr="prefetched_log_entries",
            )
            return ProblemReport.objects.select_related("reported_by_user").prefetch_related(
                latest_log_prefetch, "media"
            )

        register_feed_source(
            FeedEntrySource(
                entry_type="log",
                get_base_queryset=_log_entry_queryset,
                machine_filter_field="machine",
                global_select_related=("machine", "machine__model"),
                machine_template="maintenance/partials/log_entry.html",
                global_template="maintenance/partials/global_log_entry.html",
            )
        )
        register_feed_source(
            FeedEntrySource(
                entry_type="problem_report",
                get_base_queryset=_problem_report_queryset,
                machine_filter_field="machine",
                global_select_related=("machine", "machine__model"),
                machine_template="maintenance/partials/problem_report_entry.html",
                global_template="maintenance/partials/global_problem_report_entry.html",
            )
        )

    @staticmethod
    def _register_media_models():
        from the_flip.apps.core.models import register_media_model

        from .models import LogEntryMedia, ProblemReportMedia

        register_media_model(LogEntryMedia)
        register_media_model(ProblemReportMedia)

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
                autocomplete_search_fields=("description", "machine__name", "id"),
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
                autocomplete_search_fields=("text", "machine__name", "id"),
                autocomplete_ordering=("-created_at",),
                autocomplete_select_related=("machine",),
                autocomplete_serialize=_serialize_log,
                sort_order=40,
            )
        )
