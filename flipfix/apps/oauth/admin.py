from django.contrib import admin

from .models import AppCapability, AppCapabilityGrant


class SuperuserOnlyAdminMixin:
    """Restrict all admin operations to superusers."""

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


class AppCapabilityGrantInline(admin.TabularInline):
    model = AppCapabilityGrant
    extra = 1
    raw_id_fields = ("user", "granted_by")


@admin.register(AppCapability)
class AppCapabilityAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "app", "slug")
    list_filter = ("app",)
    search_fields = ("name", "slug")
    inlines = [AppCapabilityGrantInline]


@admin.register(AppCapabilityGrant)
class AppCapabilityGrantAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("user", "capability", "granted_by", "created_at")
    list_filter = ("capability__app", "capability")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user", "granted_by")
