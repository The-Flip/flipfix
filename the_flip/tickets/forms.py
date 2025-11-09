from django import forms
from .models import Game, ProblemReport, ReportUpdate


class ReportFilterForm(forms.Form):
    """Form for filtering problem reports in the list view."""

    STATUS_CHOICES = [
        ('all', 'All Reports'),
        (ProblemReport.STATUS_OPEN, 'Open'),
        (ProblemReport.STATUS_CLOSED, 'Closed'),
    ]

    PROBLEM_TYPE_CHOICES = [
        ('all', 'All Types'),
    ] + list(ProblemReport.PROBLEM_TYPE_CHOICES)

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

    game = forms.ModelChoiceField(
        queryset=Game.objects.exclude(status=Game.STATUS_BROKEN).order_by('name'),
        required=False,
        empty_label='All Games',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    search = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search problem text or reporter name...'
        })
    )


class ReportUpdateForm(forms.ModelForm):
    """Form for adding updates to problem reports (maintainers only)."""

    game_status = forms.ChoiceField(
        choices=[('', '-- No Change --'), (Game.STATUS_GOOD, 'Good'), (Game.STATUS_FIXING, 'Fixing'), (Game.STATUS_BROKEN, 'Broken')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Update Game Status'
    )

    class Meta:
        model = ReportUpdate
        fields = ['text', 'game_status']
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
        # Extract game if provided (for QR code scenario)
        game = kwargs.pop('game', None)
        # Extract user if provided (to hide contact fields for authenticated users)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if game:
            # QR code scenario: hide game field and pre-select
            self.fields['game'].widget = forms.HiddenInput()
            self.fields['game'].initial = game
        else:
            # General scenario: show dropdown
            self.fields['game'].queryset = Game.objects.exclude(status=Game.STATUS_BROKEN).order_by('name')
            # Customize the label to show "Name (Year Manufacturer)"
            self.fields['game'].label_from_instance = lambda obj: f"{obj.name} ({obj.year} {obj.manufacturer})"

        # Hide contact fields for authenticated users
        if user and user.is_authenticated:
            self.fields['reported_by_name'].widget = forms.HiddenInput()
            self.fields['reported_by_name'].required = False
            self.fields['reported_by_contact'].widget = forms.HiddenInput()
            self.fields['reported_by_contact'].required = False

    class Meta:
        model = ProblemReport
        fields = ['game', 'problem_type', 'problem_text', 'reported_by_name', 'reported_by_contact']
        widgets = {
            'game': forms.Select(attrs={'class': 'form-select'}),
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
            'game': 'Which game?',
            'problem_type': 'What type of problem?',
            'problem_text': 'Problem description',
            'reported_by_name': 'Your name',
            'reported_by_contact': 'Contact information',
        }
