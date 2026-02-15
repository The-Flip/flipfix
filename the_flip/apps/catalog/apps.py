from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.catalog"
    verbose_name = "Catalog"

    def ready(self):
        self._register_link_types()

    @staticmethod
    def _register_link_types():
        from the_flip.apps.core.markdown_links import LinkType, register

        def _label_with_meta(name, manufacturer, year):
            if manufacturer or year:
                parts = [p for p in [manufacturer, str(year) if year else None] if p]
                return f"{name} ({', '.join(parts)})"
            return name

        def _serialize_machine(obj):
            return {
                "label": _label_with_meta(obj.name, obj.model.manufacturer, obj.model.year),
                "ref": obj.slug,
            }

        def _serialize_model(obj):
            return {
                "label": _label_with_meta(obj.name, obj.manufacturer, obj.year),
                "ref": obj.slug,
            }

        register(
            LinkType(
                name="machine",
                model_path="catalog.MachineInstance",
                slug_field="slug",
                label="Pinball Machine",
                description="Link to a pinball machine",
                url_name="maintainer-machine-detail",
                url_kwarg="slug",
                url_field="slug",
                autocomplete_search_fields=("name", "model__name", "model__manufacturer", "slug"),
                autocomplete_ordering=("model__name",),
                autocomplete_select_related=("model",),
                autocomplete_serialize=_serialize_machine,
                sort_order=20,
            )
        )

        register(
            LinkType(
                name="model",
                model_path="catalog.MachineModel",
                slug_field="slug",
                label="Pinball Machine Model",
                description="Link to a pinball machine model",
                url_name="machine-model-edit",
                url_kwarg="slug",
                url_field="slug",
                autocomplete_search_fields=("name", "manufacturer", "slug"),
                autocomplete_ordering=("name",),
                autocomplete_serialize=_serialize_model,
                sort_order=70,
            )
        )
