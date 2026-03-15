from django.contrib import admin
from django.db.models import Count
from simple_history.admin import SimpleHistoryAdmin

from .models import Location, MachineInstance, MachineModel, Owner, OwnerDocument


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "machine_count")
    list_editable = ("sort_order",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Machines")
    def machine_count(self, obj):
        return obj.machines.count()


@admin.register(MachineModel)
class MachineModelAdmin(SimpleHistoryAdmin):
    list_display = ("name", "manufacturer", "year", "era")
    search_fields = ("name", "slug", "manufacturer", "ipdb_id")
    list_filter = ("era", "manufacturer")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("sort_name", "created_by", "updated_by")


class OwnerDocumentInline(admin.TabularInline):
    model = OwnerDocument
    extra = 0
    readonly_fields = ("uploaded_by",)


@admin.register(Owner)
class OwnerAdmin(SimpleHistoryAdmin):
    list_display = ("name", "email", "phone", "machine_count")
    search_fields = ("name", "email", "phone")
    readonly_fields = ("slug", "created_by", "updated_by")
    inlines = [OwnerDocumentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(machine_count=Count("machines"))

    @admin.display(description="Machines", ordering="machine_count")
    def machine_count(self, obj):
        return obj.machine_count


@admin.register(MachineInstance)
class MachineInstanceAdmin(SimpleHistoryAdmin):
    list_display = (
        "asset_id",
        "name",
        "short_name",
        "model",
        "owner",
        "location",
        "operational_status",
    )
    search_fields = ("asset_id", "name", "short_name", "model__name", "serial_number")
    list_filter = ("operational_status", "location", "owner")
    autocomplete_fields = ("model", "location", "owner")
    readonly_fields = ("asset_id", "slug", "created_by", "updated_by")
