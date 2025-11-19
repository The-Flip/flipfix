from django.contrib import admin

from .models import Maintainer


@admin.register(Maintainer)
class MaintainerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at", "updated_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
