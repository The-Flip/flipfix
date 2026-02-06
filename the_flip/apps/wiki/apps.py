from django.apps import AppConfig


class WikiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "the_flip.apps.wiki"
    verbose_name = "Wiki"

    def ready(self):
        from . import signals  # noqa: F401

        self._register_link_types()

    @staticmethod
    def _register_link_types():
        from django.urls import reverse

        from the_flip.apps.core.markdown_links import LinkType, register

        def _wiki_authoring_lookup(model, raw_values):
            """Custom lookup for [[page:tag/slug]] paths."""
            by_key = {}
            for raw in raw_values:
                path = raw.strip().rstrip("/")
                segments = path.split("/")
                slug = segments[-1]
                tag = "/".join(segments[:-1])
                lookup_path = f"{tag}/{slug}" if tag else slug
                if lookup_path not in by_key:
                    try:
                        pt = model.objects.select_related("page").get(tag=tag, slug=slug)
                        by_key[lookup_path] = pt
                    except model.DoesNotExist:
                        pass
            return by_key

        def _serialize_wiki_page(obj):
            ref = f"{obj.tag}/{obj.slug}" if obj.tag else obj.slug
            label = f"{obj.tag}/{obj.page.title}" if obj.tag else obj.page.title
            return {
                "label": label,
                "ref": ref,
            }

        register(
            LinkType(
                name="page",
                model_path="wiki.WikiPageTag",
                slug_field="slug",
                label="Page",
                description="Link to a page in the wiki",
                get_url=lambda pt: reverse("wiki-page-detail", kwargs={"path": str(pt)}),
                get_label=lambda pt: pt.page.title,
                select_related=("page",),
                authoring_lookup=_wiki_authoring_lookup,
                get_authoring_key=lambda pt: f"{pt.tag}/{pt.slug}" if pt.tag else pt.slug,
                autocomplete_search_fields=("page__title", "slug", "tag"),
                autocomplete_ordering=("page__title",),
                autocomplete_select_related=("page",),
                autocomplete_serialize=_serialize_wiki_page,
                sort_order=10,
            )
        )
