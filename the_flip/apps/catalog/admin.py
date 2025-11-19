from django.contrib import admin

from .models import MachineInstance, MachineModel


@admin.register(MachineModel)
class MachineModelAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer", "year", "era")
    search_fields = ("name", "slug", "manufacturer", "ipdb_id")
    list_filter = ("era", "manufacturer")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_by", "updated_by")


@admin.register(MachineInstance)
class MachineInstanceAdmin(admin.ModelAdmin):
    list_display = ("display_name", "model", "location", "operational_status")
    search_fields = ("name_override", "model__name", "serial_number")
    list_filter = ("operational_status", "location")
    autocomplete_fields = ("model",)
    readonly_fields = ("slug", "created_by", "updated_by")
