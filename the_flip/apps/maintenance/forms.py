"""Forms for maintenance workflows."""
from django import forms

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia, ProblemReport


class ProblemReportForm(forms.ModelForm):
    class Meta:
        model = ProblemReport
        fields = ["problem_type", "description", "reported_by_name", "reported_by_contact", "device_info"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class LogEntryForm(forms.ModelForm):
    maintainers = forms.ModelMultipleChoiceField(
        queryset=Maintainer.objects.select_related("user"),
        required=False,
        help_text="Select maintainers credited for this work.",
    )

    class Meta:
        model = LogEntry
        fields = ["text", "maintainers", "maintainer_names", "machine_status", "problem_report_status", "problem_report"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 4}),
        }


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
