from django.contrib import admin


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
    readonly_fields = (
        "thumbnail_file",
        "transcoded_file",
        "poster_file",
        "transcode_status",
    )
