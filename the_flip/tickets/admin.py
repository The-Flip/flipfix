from django.contrib import admin
from .models import Game, Maintainer, ProblemReport, ReportUpdate


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['name', 'manufacturer', 'year', 'type', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['name', 'manufacturer']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Maintainer)
class MaintainerAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'is_active']
    list_filter = ['is_active']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'phone']


@admin.register(ProblemReport)
class ProblemReportAdmin(admin.ModelAdmin):
    list_display = ['game', 'problem_type', 'status', 'created_at', 'reported_by']
    list_filter = ['status', 'problem_type', 'created_at']
    search_fields = ['game__name', 'problem_text', 'reported_by_name']
    readonly_fields = ['created_at']

    @admin.display(description='Reported By')
    def reported_by(self, obj):
        if obj.reported_by_user:
            return obj.reported_by_user.username
        return obj.reported_by_name or 'Anonymous'


@admin.register(ReportUpdate)
class ReportUpdateAdmin(admin.ModelAdmin):
    list_display = ['report', 'maintainer', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['report__game__name', 'text']
    readonly_fields = ['created_at']
