from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import WikiPage, WikiPageTag, WikiTagOrder


class WikiPageTagInline(admin.TabularInline):
    model = WikiPageTag
    extra = 1
    fields = ("tag", "slug", "order")
    readonly_fields = ("slug",)

    def get_readonly_fields(self, request, obj=None):
        """Slug is auto-synced from page, so always readonly."""
        return self.readonly_fields


@admin.register(WikiPage)
class WikiPageAdmin(SimpleHistoryAdmin):
    list_display = ("title", "slug", "tag_list", "updated_at", "updated_by")
    list_filter = ("created_at", "updated_at")
    search_fields = ("title", "slug", "content", "tags__tag")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "content")
    inlines = (WikiPageTagInline,)

    fieldsets = (
        (None, {"fields": ("title", "slug", "content")}),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Auto-populate created_by and updated_by from current user."""
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("created_by", "updated_by").prefetch_related("tags")

    @admin.display(description="Tags")
    def tag_list(self, obj):
        tags = [t.tag or "(root)" for t in obj.tags.all()]
        return ", ".join(tags) if tags else "-"

    def save_formset(self, request, form, formset, change):
        """Ensure WikiPageTag.slug is synced from WikiPage.slug on save."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, WikiPageTag):
                instance.slug = form.instance.slug
            instance.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()


@admin.register(WikiPageTag)
class WikiPageTagAdmin(admin.ModelAdmin):
    list_display = ("page", "tag", "slug", "order")
    list_filter = ("tag",)
    search_fields = ("page__title", "page__slug", "tag", "slug")
    autocomplete_fields = ("page",)
    readonly_fields = ("slug",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("page")


@admin.register(WikiTagOrder)
class WikiTagOrderAdmin(admin.ModelAdmin):
    list_display = ("tag", "order")
    list_editable = ("order",)
    search_fields = ("tag",)
    ordering = ("order",)
