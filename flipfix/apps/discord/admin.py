"""Admin interface for Discord integration."""

from django.contrib import admin

from .models import DiscordUserLink, PendingNotification


@admin.register(DiscordUserLink)
class DiscordUserLinkAdmin(admin.ModelAdmin):
    list_display = (
        "discord_display_name",
        "discord_username",
        "maintainer",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "discord_username",
        "discord_display_name",
        "maintainer__user__username",
        "maintainer__user__first_name",
        "maintainer__user__last_name",
    )
    readonly_fields = ("created_at", "updated_at", "discord_avatar_url")
    autocomplete_fields = ("maintainer",)
    fieldsets = (
        (
            "Discord User",
            {
                "fields": (
                    "discord_user_id",
                    "discord_username",
                    "discord_display_name",
                    "discord_avatar_url",
                )
            },
        ),
        ("Linked Maintainer", {"fields": ("maintainer",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(PendingNotification)
class PendingNotificationAdmin(admin.ModelAdmin):
    """Read-only view of the debounced notification buffer (for observability)."""

    list_display = ("handler_name", "object_id", "actor", "buffered_at", "sent_at")
    list_filter = ("handler_name", "sent_at")
    search_fields = ("actor__username", "actor__first_name", "actor__last_name")
    readonly_fields = ("handler_name", "object_id", "actor", "buffered_at", "sent_at")
    date_hierarchy = "buffered_at"

    def has_add_permission(self, request) -> bool:
        return False
