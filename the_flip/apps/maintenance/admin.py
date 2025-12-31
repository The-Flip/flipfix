from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import LogEntry, LogEntryMedia, ProblemReport, ProblemReportMedia


class LogEntryAdminForm(forms.ModelForm):
    class Meta:
        model = LogEntry
        fields = (
            "machine",
            "problem_report",
            "maintainers",
            "maintainer_names",
            "text",
            "occurred_at",
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


class ProblemReportMediaInline(admin.TabularInline):
    model = ProblemReportMedia
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
class ProblemReportAdmin(SimpleHistoryAdmin):
    list_display = ("machine", "problem_type", "status", "reporter_display", "occurred_at")
    list_filter = ("status", "problem_type", "machine__location")
    search_fields = (
        "description",
        "reported_by_name",
        "reported_by_contact",
        "machine__name",
        "machine__model__name",
    )
    autocomplete_fields = ("machine", "reported_by_user")
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProblemReportMediaInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("machine", "reported_by_user")


@admin.register(LogEntry)
class LogEntryAdmin(SimpleHistoryAdmin):
    list_display = ("machine", "occurred_at", "problem_report", "maintainer_list", "created_by")
    list_filter = ("machine__location", "problem_report__status")
    search_fields = (
        "text",
        "maintainer_names",
        "maintainers__user__username",
        "maintainers__user__first_name",
        "maintainers__user__last_name",
        "machine__name",
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
class LogEntryMediaAdmin(SimpleHistoryAdmin):
    list_display = ("log_entry", "media_type", "transcode_status", "created_at")
    list_filter = ("media_type", "transcode_status")
    search_fields = (
        "log_entry__machine__name",
        "log_entry__machine__model__name",
        "log_entry__text",
    )
    autocomplete_fields = ("log_entry",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProblemReportMedia)
class ProblemReportMediaAdmin(SimpleHistoryAdmin):
    list_display = ("problem_report", "media_type", "transcode_status", "created_at")
    list_filter = ("media_type", "transcode_status")
    search_fields = (
        "problem_report__machine__name",
        "problem_report__machine__model__name",
        "problem_report__description",
    )
    autocomplete_fields = ("problem_report",)
    readonly_fields = ("created_at", "updated_at")
