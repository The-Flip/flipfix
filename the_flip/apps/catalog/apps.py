from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.catalog"
    verbose_name = "Catalog"

    def ready(self):
        from the_flip.apps.catalog import signals  # noqa: F401

        self._register_link_types()

    @staticmethod
    def _register_link_types():
        from the_flip.apps.core.markdown_links import LinkType, register

        def _serialize_machine(obj):
            label = obj.name
            if obj.model.manufacturer or obj.model.year:
                parts = []
                if obj.model.manufacturer:
                    parts.append(obj.model.manufacturer)
                if obj.model.year:
                    parts.append(str(obj.model.year))
                label = f"{obj.name} ({', '.join(parts)})"
            return {"label": label, "ref": obj.slug}

        def _serialize_model(obj):
            label = obj.name
            if obj.manufacturer or obj.year:
                parts = []
                if obj.manufacturer:
                    parts.append(obj.manufacturer)
                if obj.year:
                    parts.append(str(obj.year))
                label = f"{obj.name} ({', '.join(parts)})"
            return {"label": label, "ref": obj.slug}

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
                autocomplete_search_fields=("name", "model__name", "slug"),
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
