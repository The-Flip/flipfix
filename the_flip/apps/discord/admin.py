"""Admin interface for Discord integration."""

from django.contrib import admin

from .models import DiscordUserLink


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
