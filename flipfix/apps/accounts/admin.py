from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from flipfix.apps.core.admin import MediaInline

from .models import Invitation, Maintainer, MaintainerMedia


class MaintainerMediaInline(MediaInline):
    """Inline admin for maintainer profile media."""

    model = MaintainerMedia


@admin.register(Maintainer)
class MaintainerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at", "updated_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    inlines = [MaintainerMediaInline]


@admin.register(MaintainerMedia)
class MaintainerMediaAdmin(SimpleHistoryAdmin):
    """Admin for maintainer profile media."""

    list_display = ["id", "maintainer", "media_type", "transcode_status", "created_at"]
    list_filter = ["media_type", "transcode_status"]
    search_fields = ["maintainer__user__username"]
    readonly_fields = ["created_at", "updated_at", "transcode_status"]
    ordering = ["-created_at"]

    def get_readonly_fields(self, request, obj=None):
        # ``media_type`` must be set at create time (no default; gates
        # AbstractMedia.save() upload processing), but should be locked
        # afterwards so the classification can't drift from the file.
        base = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            base.append("media_type")
        return base


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    """Superuser fallback for the maintainer-facing invite pages.

    Everyday invitations are created at ``/invites/`` by any maintainer with
    ``can_invite_users``. This exists for the cases the UI deliberately
    doesn't cover — correcting a typo'd address, or inspecting somebody
    else's invitation without walking the tree. The shareable link lives on
    the invite detail page, which has a request to build an absolute URL
    from; this one just points at it.
    """

    list_display = ("email", "status_label", "invited_by", "accepted_by", "created_at")
    # ``status`` is derived from the timestamps, so it cannot be filtered on
    # directly. These two EmptyFieldListFilters cover the same ground:
    # accepted yes/no and revoked yes/no.
    list_filter = (
        ("accepted_at", admin.EmptyFieldListFilter),
        ("revoked_at", admin.EmptyFieldListFilter),
    )
    search_fields = ("email", "invited_by__username", "accepted_by__username")
    readonly_fields = (
        "token",
        "invite_page",
        "accepted_by",
        "accepted_at",
        "last_sent_at",
        "created_at",
    )
    raw_id_fields = ("invited_by",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("invited_by", "accepted_by")

    def get_fields(self, request, obj=None):
        """Show different fields for add vs change views."""
        if obj:  # Editing existing invitation
            return (
                "email",
                "invite_page",
                "invited_by",
                "accepted_by",
                "accepted_at",
                "revoked_at",
                "expires_at",
                "last_sent_at",
                "created_at",
            )
        else:  # Adding new invitation
            return ("email", "invited_by")

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
        """After creating an invitation, send the superuser to its invite page.

        That page renders the absolute shareable link and the resend button;
        the admin change form has neither.
        """
        return HttpResponseRedirect(obj.get_absolute_url())

    @admin.display(description="Status")
    def status_label(self, obj):
        return obj.status_label

    @admin.display(description="Invite page")
    def invite_page(self, obj):
        if not obj.pk:
            return "Save to generate the invitation link"
        url = obj.get_absolute_url()
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
