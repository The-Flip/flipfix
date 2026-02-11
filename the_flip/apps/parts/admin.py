"""Admin configuration for parts app."""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from the_flip.apps.core.admin import MediaInline
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


class PartRequestMediaInline(MediaInline):
    """Inline admin for part request media."""

    model = PartRequestMedia


class PartRequestUpdateInline(admin.TabularInline):
    """Inline admin for part request updates."""

    model = PartRequestUpdate
    extra = 0
    fields = ["posted_by", "text", "new_status", "occurred_at"]
    ordering = ["-occurred_at"]


@admin.register(PartRequest)
class PartRequestAdmin(SimpleHistoryAdmin):
    """Admin for part requests."""

    list_display = [
        "id",
        "text_preview",
        "status",
        "requested_by",
        "machine",
        "occurred_at",
    ]
    list_filter = ["status", "occurred_at"]
    search_fields = ["text", "requested_by__user__username", "machine__model__name"]
    readonly_fields = ["created_at", "updated_at", "text"]
    autocomplete_fields = ["requested_by", "machine"]
    inlines = [PartRequestMediaInline, PartRequestUpdateInline]
    ordering = ["-occurred_at"]

    @admin.display(description="Description")
    def text_preview(self, obj):
        """Return truncated text preview."""
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text


@admin.register(PartRequestMedia)
class PartRequestMediaAdmin(SimpleHistoryAdmin):
    """Admin for part request media."""

    list_display = ["id", "part_request", "media_type", "transcode_status", "created_at"]
    list_filter = ["media_type", "transcode_status"]
    search_fields = ["part_request__text"]
    readonly_fields = ["created_at", "updated_at", "transcode_status"]
    ordering = ["-created_at"]


class PartRequestUpdateMediaInline(MediaInline):
    """Inline admin for part request update media."""

    model = PartRequestUpdateMedia


@admin.register(PartRequestUpdate)
class PartRequestUpdateAdmin(SimpleHistoryAdmin):
    """Admin for part request updates."""

    list_display = [
        "id",
        "text_preview",
        "part_request",
        "posted_by",
        "new_status",
        "occurred_at",
    ]
    list_filter = ["new_status", "occurred_at"]
    search_fields = ["text", "posted_by__user__username", "part_request__text"]
    readonly_fields = ["created_at", "updated_at", "text"]
    autocomplete_fields = ["posted_by", "part_request"]
    inlines = [PartRequestUpdateMediaInline]
    ordering = ["-occurred_at"]

    @admin.display(description="Comment")
    def text_preview(self, obj):
        """Return truncated text preview."""
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text


@admin.register(PartRequestUpdateMedia)
class PartRequestUpdateMediaAdmin(SimpleHistoryAdmin):
    """Admin for part request update media."""

    list_display = ["id", "update", "media_type", "transcode_status", "created_at"]
    list_filter = ["media_type", "transcode_status"]
    search_fields = ["update__text"]
    readonly_fields = ["created_at", "updated_at", "transcode_status"]
    ordering = ["-created_at"]
