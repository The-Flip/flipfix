"""Parts app configuration."""

from django.apps import AppConfig


class PartsConfig(AppConfig):
    """Configuration for the parts app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.parts"
    verbose_name = "Parts Management"

    def ready(self):
        from the_flip.apps.core.models import register_reference_cleanup

        from .models import PartRequest, PartRequestUpdate

        register_reference_cleanup(PartRequest, PartRequestUpdate)

        self._register_link_types()
        self._register_media_models()

    @staticmethod
    def _register_media_models():
        from the_flip.apps.core.models import register_media_model

        from .models import PartRequestMedia, PartRequestUpdateMedia

        register_media_model(PartRequestMedia)
        register_media_model(PartRequestUpdateMedia)

    @staticmethod
    def _register_link_types():
        from the_flip.apps.core.markdown_links import LinkType, link_preview, register

        def _partrequest_label(obj):
            label = f"Part Request #{obj.pk}"
            if obj.text:
                label += f": {link_preview(obj.text)}"
            return label

        def _partrequestupdate_label(obj):
            label = f"Update #{obj.pk} on #{obj.part_request_id}"
            if obj.text:
                label += f": {link_preview(obj.text)}"
            return label

        def _serialize_partrequest(obj):
            return {
                "label": f"#{obj.pk}: {(obj.text or '')[:50]}",
                "ref": str(obj.pk),
            }

        def _serialize_partrequestupdate(obj):
            label = f"#{obj.pk}: Update on #{obj.part_request_id}"
            if obj.text:
                label += f": {obj.text[:20]}"
            return {
                "label": label,
                "ref": str(obj.pk),
            }

        register(
            LinkType(
                name="partrequest",
                model_path="parts.PartRequest",
                label="Parts Request",
                description="Link to a parts request",
                url_name="part-request-detail",
                get_label=_partrequest_label,
                autocomplete_search_fields=("text", "machine__name", "id"),
                autocomplete_ordering=("-created_at",),
                autocomplete_select_related=("machine",),
                autocomplete_serialize=_serialize_partrequest,
                sort_order=50,
            )
        )

        register(
            LinkType(
                name="partrequestupdate",
                model_path="parts.PartRequestUpdate",
                label="Parts Update",
                description="Link to an update on a parts request",
                url_name="part-request-detail",
                url_field="part_request_id",
                get_label=_partrequestupdate_label,
                select_related=("part_request",),
                autocomplete_search_fields=("text", "part_request__machine__name", "id"),
                autocomplete_ordering=("-created_at",),
                autocomplete_select_related=("part_request",),
                autocomplete_serialize=_serialize_partrequestupdate,
                sort_order=60,
            )
        )
