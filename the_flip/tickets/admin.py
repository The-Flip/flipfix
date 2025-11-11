from django.contrib import admin
from django.contrib.admin import AdminSite
from django import forms
from .models import MachineModel, MachineInstance, Maintainer, Task, LogEntry


class CustomAdminSite(AdminSite):
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all the installed apps with custom model ordering.
        """
        app_list = super().get_app_list(request, app_label)

        # Custom ordering for app sections
        app_order = {
            'auth': 1,
            'games': 2,
            'tickets': 3,
        }

        # Custom ordering for Authentication and Authorization models
        auth_order = {
            'Groups': 1,
            'Users': 2,
            'Maintainers': 3,
        }

        # Custom ordering for Game Maintenance models
        game_maintenance_order = {
            'Tasks': 1,
            'Log Entries': 2,
        }

        # Custom ordering for Games app models
        games_order = {
            'Machine Models': 1,
            'Machine Instances': 2,
        }

        for app in app_list:
            if app['app_label'] == 'auth':
                app['models'].sort(key=lambda x: auth_order.get(x['name'], 999))
            elif app['app_label'] == 'tickets':
                app['models'].sort(key=lambda x: game_maintenance_order.get(x['name'], 999))
            elif app['app_label'] == 'games':
                app['models'].sort(key=lambda x: games_order.get(x['name'], 999))

        # Sort apps by custom order
        app_list = sorted(app_list, key=lambda x: app_order.get(x['app_label'], 999))

        return app_list


# Override the default admin site
admin.site.__class__ = CustomAdminSite


class MachineModelAdminProxy(MachineModel):
    """Proxy model to display Machine Models under the Games app section."""
    class Meta:
        proxy = True
        app_label = 'games'
        verbose_name = 'Machine Model'
        verbose_name_plural = 'Machine Models'


class MachineModelAdminForm(forms.ModelForm):
    class Meta:
        model = MachineModelAdminProxy
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the era field to use only the defined choices without a blank option
        self.fields['era'].choices = MachineModel.ERA_CHOICES
        self.fields['era'].required = True


@admin.register(MachineModelAdminProxy)
class MachineModelAdmin(admin.ModelAdmin):
    form = MachineModelAdminForm
    list_display = ['name', 'manufacturer', 'year', 'era', 'system', 'pinside_rating']
    list_filter = ['era', 'manufacturer', 'year']
    search_fields = ['name', 'manufacturer', 'system']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'manufacturer', 'month', 'year', 'era')
        }),
        ('Technical Details', {
            'fields': ('system', 'scoring', 'flipper_count')
        }),
        ('Production', {
            'fields': ('production_quantity', 'factory_address')
        }),
        ('Credits', {
            'fields': ('design_credit', 'concept_and_design_credit', 'art_credit', 'sound_credit')
        }),
        ('Educational Content', {
            'fields': ('educational_text', 'illustration_filename', 'sources_notes'),
            'classes': ('collapse',)
        }),
        ('Community', {
            'fields': ('pinside_rating', 'ipdb_id')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )


class MachineInstanceAdminProxy(MachineInstance):
    """Proxy model to display Machine Instances under the Games app section."""
    class Meta:
        proxy = True
        app_label = 'games'
        verbose_name = 'Machine Instance'
        verbose_name_plural = 'Machine Instances'


class MachineInstanceAdminForm(forms.ModelForm):
    class Meta:
        model = MachineInstanceAdminProxy
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the operational_status field to use only the defined choices without a blank option
        self.fields['operational_status'].choices = MachineInstance.OPERATIONAL_STATUS_CHOICES
        self.fields['operational_status'].required = True
        # Set the location field choices if location is provided
        if 'location' in self.fields:
            self.fields['location'].choices = [('', '---------')] + list(MachineInstance.LOCATION_CHOICES)


@admin.register(MachineInstanceAdminProxy)
class MachineInstanceAdmin(admin.ModelAdmin):
    form = MachineInstanceAdminForm
    list_display = ['name', 'model', 'serial_number', 'location', 'operational_status']
    list_filter = ['location', 'operational_status', 'model__era', 'model__manufacturer']
    search_fields = ['name_override', 'model__name', 'model__manufacturer', 'serial_number']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    fieldsets = (
        ('Identity', {
            'fields': ('model', 'name_override', 'slug')
        }),
        ('Physical Identification', {
            'fields': ('serial_number',)
        }),
        ('Acquisition', {
            'fields': ('acquisition_notes', 'ownership_credit'),
            'classes': ('collapse',)
        }),
        ('Location & Status', {
            'fields': ('location', 'operational_status')
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


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['machine', 'type', 'problem_type', 'status', 'created_at', 'reported_by']
    list_filter = ['type', 'status', 'problem_type', 'created_at']
    search_fields = ['machine__name_override', 'machine__model__name', 'problem_text', 'reported_by_name']
    readonly_fields = ['created_at']

    @admin.display(description='Reported By')
    def reported_by(self, obj):
        if obj.reported_by_user:
            return obj.reported_by_user.username
        return obj.reported_by_name or 'Anonymous'


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ['task', 'get_maintainers', 'status', 'machine_status', 'created_at']
    list_filter = ['status', 'machine_status', 'created_at']
    search_fields = ['task__machine__name_override', 'task__machine__model__name', 'text']
    readonly_fields = ['created_at']
    filter_horizontal = ['maintainers']

    @admin.display(description='Maintainers')
    def get_maintainers(self, obj):
        return ", ".join([str(m) for m in obj.maintainers.all()[:3]])
