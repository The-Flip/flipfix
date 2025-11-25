from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .models import Invitation, Maintainer


@admin.register(Maintainer)
class MaintainerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at", "updated_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "used", "created_at")
    list_filter = ("used",)
    search_fields = ("email",)
    readonly_fields = ("token", "used", "registration_link", "created_at")

    def get_fields(self, request, obj=None):
        """Show different fields for add vs change views."""
        if obj:  # Editing existing invitation
            return ("email", "registration_link", "used", "created_at")
        else:  # Adding new invitation
            return ("email",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def response_add(self, request, obj, post_url_continue=None):
        """After creating an invitation, redirect to its detail page to show the link."""
        return HttpResponseRedirect(reverse("admin:accounts_invitation_change", args=[obj.pk]))

    @admin.display(description="Registration Link")
    def registration_link(self, obj):
        if obj.pk and not obj.used:
            url = reverse("invitation-register", kwargs={"token": obj.token})
            # Build absolute URL manually since we don't have request in this context
            return format_html(
                '<a href="{}" target="_blank">{}</a><br>'
                '<input type="text" value="{}" readonly style="width:400px;" '
                'onclick="this.select();">',
                url,
                url,
                url,
            )
        elif obj.used:
            return "Invitation already used"
        return "Save to generate link"
