from django import forms
from django.contrib import admin

from .models import LogEntry, LogEntryMedia, ProblemReport


class LogEntryAdminForm(forms.ModelForm):
    class Meta:
        model = LogEntry
        fields = (
            "machine",
            "problem_report",
            "maintainers",
            "maintainer_names",
            "text",
            "work_date",
            "created_by",
        )

    def clean(self):
        cleaned = super().clean()
        # Allow model validation to see unsaved M2M data
        self.instance._pending_maintainers = cleaned.get("maintainers")
        return cleaned


class LogEntryMediaInline(admin.TabularInline):
    model = LogEntryMedia
    extra = 0
    fields = (
        "media_type",
        "file",
        "thumbnail_file",
        "transcoded_file",
        "poster_file",
        "transcode_status",
        "display_order",
    )


@admin.register(ProblemReport)
class ProblemReportAdmin(admin.ModelAdmin):
    list_display = ("machine", "problem_type", "status", "reporter_display", "created_at")
    list_filter = ("status", "problem_type", "machine__location")
    search_fields = (
        "description",
        "reported_by_name",
        "reported_by_contact",
        "machine__name_override",
        "machine__model__name",
    )
    autocomplete_fields = ("machine", "reported_by_user")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("machine", "reported_by_user")


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ("machine", "work_date", "problem_report", "maintainer_list", "created_by")
    list_filter = ("machine__location", "problem_report__status")
    search_fields = (
        "text",
        "maintainer_names",
        "maintainers__user__username",
        "maintainers__user__first_name",
        "maintainers__user__last_name",
        "machine__name_override",
        "machine__model__name",
        "problem_report__description",
    )
    autocomplete_fields = ("machine", "problem_report", "maintainers", "created_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = (LogEntryMediaInline,)
    form = LogEntryAdminForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("machine", "problem_report", "created_by").prefetch_related(
            "maintainers"
        )

    @admin.display(description="Maintainers")
    def maintainer_list(self, obj):
        names = [m.display_name for m in obj.maintainers.all()]
        if obj.maintainer_names:
            names.append(obj.maintainer_names)
        return ", ".join(names) if names else "-"


@admin.register(LogEntryMedia)
class LogEntryMediaAdmin(admin.ModelAdmin):
    list_display = ("log_entry", "media_type", "transcode_status", "created_at")
    list_filter = ("media_type", "transcode_status")
    search_fields = (
        "log_entry__machine__name_override",
        "log_entry__machine__model__name",
        "log_entry__text",
    )
    autocomplete_fields = ("log_entry",)
    readonly_fields = ("created_at", "updated_at")
