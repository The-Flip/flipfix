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
        initial='all',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    problem_type = forms.ChoiceField(
        choices=PROBLEM_TYPE_CHOICES,
        required=False,
        initial='all',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    game = forms.ModelChoiceField(
        queryset=Game.objects.filter(is_active=True).order_by('name'),
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

    class Meta:
        model = ReportUpdate
        fields = ['text']
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
