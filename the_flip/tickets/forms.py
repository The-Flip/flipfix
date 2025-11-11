from django import forms
from .models import MachineModel, MachineInstance, Task, LogEntry


class GameFilterForm(forms.Form):
    """Form for filtering machine instances in the list view."""

    ERA_CHOICES = [
        ('', 'All Eras'),
    ] + list(MachineModel.ERA_CHOICES)

    LOCATION_CHOICES = [
        ('', 'All Locations'),
    ] + list(MachineInstance.LOCATION_CHOICES)

    OPERATIONAL_STATUS_CHOICES = [
        ('', 'All Statuses'),
    ] + list(MachineInstance.OPERATIONAL_STATUS_CHOICES)

    search = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Machine name, manufacturer, or serial number'
        })
    )

    era = forms.ChoiceField(
        choices=ERA_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    location = forms.ChoiceField(
        choices=LOCATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    operational_status = forms.ChoiceField(
        choices=OPERATIONAL_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Status'
    )


class ReportFilterForm(forms.Form):
    """Form for filtering problem reports in the list view."""

    STATUS_CHOICES = [
        ('all', 'All Reports'),
        (Task.STATUS_OPEN, 'Open'),
        (Task.STATUS_CLOSED, 'Closed'),
    ]

    PROBLEM_TYPE_CHOICES = [
        ('all', 'All Types'),
    ] + list(Task.PROBLEM_TYPE_CHOICES)

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        initial='open',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    problem_type = forms.ChoiceField(
        choices=PROBLEM_TYPE_CHOICES,
        required=False,
        initial='all',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    machine = forms.ModelChoiceField(
        queryset=MachineInstance.objects.none(),
        required=False,
        empty_label='All Machines',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    search = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search machine name, problem text, or reporter name...'
        })
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['machine'].queryset = MachineInstance.objects.exclude(
            operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN
        ).select_related('model').order_by('model__name', 'serial_number')


class LogEntryForm(forms.ModelForm):
    """Form for adding log entries to tasks (maintainers only)."""

    machine_status = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Update Machine Status'
    )

    def __init__(self, *args, **kwargs):
        # Extract current_machine_status if provided
        current_machine_status = kwargs.pop('current_machine_status', None)
        super().__init__(*args, **kwargs)

        # Build choices from MachineInstance.OPERATIONAL_STATUS_CHOICES, excluding UNKNOWN and current status
        available_choices = [('', '-- No Change --')]
        for status_code, status_label in MachineInstance.OPERATIONAL_STATUS_CHOICES:
            if status_code in {MachineInstance.OPERATIONAL_STATUS_UNKNOWN}:  # Skip unknown status for updates
                continue
            if status_code == current_machine_status:
                continue
            available_choices.append((status_code, status_label))

        self.fields['machine_status'].choices = available_choices

    class Meta:
        model = LogEntry
        fields = ['text', 'machine_status']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Add your update or notes here...'
            })
        }
        labels = {
            'text': 'Update'
        }


class ProblemReportCreateForm(forms.ModelForm):
    """Form for creating new problem reports (public + maintainers)."""

    def __init__(self, *args, **kwargs):
        # Extract machine if provided (for QR code scenario)
        machine = kwargs.pop('machine', None)
        # Extract user if provided (to hide contact fields for authenticated users)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if machine:
            # QR code scenario: hide machine field and pre-select
            self.fields['machine'].widget = forms.HiddenInput()
            self.fields['machine'].initial = machine
        else:
            # General scenario: show dropdown
            if user and user.is_authenticated:
                # Authenticated users: show all machines regardless of location or status
                queryset = MachineInstance.objects.all()
            else:
                # Unauthenticated users: only show machines on the floor
                queryset = MachineInstance.objects.filter(location=MachineInstance.LOCATION_FLOOR)

            self.fields['machine'].queryset = queryset.select_related('model').order_by('model__name', 'serial_number')
            # Customize the label to show "Name (Year Manufacturer)"
            self.fields['machine'].label_from_instance = lambda obj: f"{obj.name} ({obj.model.year} {obj.model.manufacturer})"

        # Hide contact fields for authenticated users
        if user and user.is_authenticated:
            self.fields['reported_by_name'].widget = forms.HiddenInput()
            self.fields['reported_by_name'].required = False
            self.fields['reported_by_contact'].widget = forms.HiddenInput()
            self.fields['reported_by_contact'].required = False

    def save(self, commit=True):
        """Override save to set type to problem_report."""
        instance = super().save(commit=False)
        instance.type = Task.TYPE_PROBLEM_REPORT
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Task
        fields = ['machine', 'problem_type', 'problem_text', 'reported_by_name', 'reported_by_contact']
        widgets = {
            'machine': forms.Select(attrs={'class': 'form-select'}),
            'problem_type': forms.RadioSelect(),
            'problem_text': forms.Textarea(attrs={
                'rows': 5,
                'class': 'form-control',
                'placeholder': 'Please describe the problem in detail...'
            }),
            'reported_by_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your name (optional)'
            }),
            'reported_by_contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email or phone (optional)'
            }),
        }
        labels = {
            'machine': 'Which machine?',
            'problem_type': 'What type of problem?',
            'problem_text': 'Problem description',
            'reported_by_name': 'Your name',
            'reported_by_contact': 'Contact information',
        }
