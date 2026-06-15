from django.contrib import admin

from flipfix.apps.core.models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("app_name", "key_preview", "can_write", "created_at")
    list_filter = ("can_write",)
    readonly_fields = ("key", "created_at")
    search_fields = ("app_name",)

    @admin.display(description="Key")
    def key_preview(self, obj: ApiKey) -> str:
        return f"{obj.key[:8]}..."


class MediaInline(admin.TabularInline):
    """Base inline for models that inherit from AbstractMedia.

    Subclasses need only set ``model``. Override ``fields`` or
    ``readonly_fields`` if a particular media model diverges from
    the common set.
    """

    extra = 0
    fields = (
        "media_type",
        "file",
        "thumbnail_file",
        "transcoded_file",
        "poster_file",
        "transcode_status",
        "display_order",
    )
    # ``media_type`` is intentionally editable: it has no default and gates
    # upload processing in AbstractMedia.save(), so admin-added rows would
    # save with an empty classification if it were read-only.
    readonly_fields = (
        "thumbnail_file",
        "transcoded_file",
        "poster_file",
        "transcode_status",
    )
