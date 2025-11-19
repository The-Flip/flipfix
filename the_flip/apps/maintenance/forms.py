"""Forms for maintenance workflows."""
from django import forms

from the_flip.apps.maintenance.models import ProblemReport


class ProblemReportForm(forms.ModelForm):
    class Meta:
        model = ProblemReport
        fields = ["problem_type", "description"]
        widgets = {
            "problem_type": forms.RadioSelect(),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe the problem..."}),
        }
        labels = {
            "problem_type": "What type of problem?",
            "description": "",
        }


class MachineReportSearchForm(forms.Form):
    q = forms.CharField(
        label="Search",
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Search..."}),
    )


class LogEntryQuickForm(forms.Form):
    submitter_name = forms.CharField(
        label="Your name",
        max_length=200,
        widget=forms.TextInput(attrs={"enterkeyhint": "next", "autocomplete": "name"}),
    )
    text = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What work was done?", "autofocus": True}),
        max_length=1000,
    )
    photo = forms.ImageField(
        label="Photo",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
