from django.contrib import admin

from .models import AppCapability, AppCapabilityGrant


class AppCapabilityGrantInline(admin.TabularInline):
    model = AppCapabilityGrant
    extra = 1
    raw_id_fields = ("user", "granted_by")


@admin.register(AppCapability)
class AppCapabilityAdmin(admin.ModelAdmin):
    list_display = ("name", "app", "slug")
    list_filter = ("app",)
    search_fields = ("name", "slug")
    inlines = [AppCapabilityGrantInline]

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


@admin.register(AppCapabilityGrant)
class AppCapabilityGrantAdmin(admin.ModelAdmin):
    list_display = ("user", "capability", "granted_by", "created_at")
    list_filter = ("capability__app", "capability")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user", "granted_by")

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
