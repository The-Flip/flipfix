from django.contrib import admin
from django import forms
from .models import Game, Maintainer, ProblemReport, ReportUpdate


class GameAdminForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the type field to use only the defined choices without a blank option
        self.fields['type'].choices = Game.TYPE_CHOICES
        self.fields['type'].required = True
        # Set the status field to use only the defined choices without a blank option
        self.fields['status'].choices = Game.STATUS_CHOICES
        self.fields['status'].required = True


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    form = GameAdminForm
    list_display = ['name', 'manufacturer', 'year', 'type', 'system', 'pinside_rating', 'status']
    list_filter = ['type', 'status', 'system']
    search_fields = ['name', 'manufacturer', 'system']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'manufacturer', 'month', 'year')
        }),
        ('Technical Details', {
            'fields': ('type', 'system', 'scoring', 'flipper_count')
        }),
        ('Community', {
            'fields': ('pinside_rating', 'ipdb_url')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )


class MaintainerAdminProxy(Maintainer):
    """Proxy model to display Maintainers under Authentication and Authorization."""
    class Meta:
        proxy = True
        app_label = 'auth'
        verbose_name = 'Maintainer'
        verbose_name_plural = 'Maintainers'


@admin.register(MaintainerAdminProxy)
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
