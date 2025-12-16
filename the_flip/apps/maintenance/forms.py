"""Forms for maintenance workflows."""

from django import forms
from django.utils import timezone

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import (
    StyledFormMixin,
    collect_media_files,
    validate_media_files,
)
from the_flip.apps.maintenance.models import ProblemReport


class MultiFileInput(forms.ClearableFileInput):
    """Clearable file input that allows selecting multiple files."""

    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    """FileField that returns a list of uploaded files when multiple are provided."""

    widget = MultiFileInput

    def to_python(self, data):
        if not data:
            return []
        if isinstance(data, list | tuple):
            return list(data)
        # Single file falls back to base implementation
        single = super().to_python(data)
        return [single] if single else []

    def validate(self, data):
        # Skip base class validation; validate each file individually
        if not data:
            return
        errors = []
        for f in data:
            try:
                super().validate(f)
                self.run_validators(f)
            except forms.ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            raise forms.ValidationError(errors)


class ProblemReportForm(StyledFormMixin, forms.ModelForm):
    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ProblemReport
        fields = ["problem_type", "description"]
        widgets = {
            "problem_type": forms.RadioSelect(),
            "description": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Describe the problem..."}
            ),
        }
        labels = {
            "problem_type": "What type of problem?",
            "description": "",
        }

    def clean_machine_slug(self):
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a machine.")

    def clean(self):
        cleaned = super().clean()
        problem_type = cleaned.get("problem_type")
        description = (cleaned.get("description") or "").strip()
        if problem_type == ProblemReport.PROBLEM_OTHER and not description:
            self.add_error("description", "Please describe the problem.")
        return cleaned


class MaintainerProblemReportForm(ProblemReportForm):
    """Extended problem report form for maintainers with media upload support.

    Unlike the public form, maintainers don't select a problem type - it defaults to "Other".
    Description is still required.
    """

    class Meta(ProblemReportForm.Meta):
        fields = ["description"]  # Exclude problem_type; model defaults to "Other"

    reporter_name = forms.CharField(
        label="Reporter name",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Who is reporting this?"}),
    )

    media_file = MultiFileField(
        label="Photo",
        required=False,
        widget=MultiFileInput(
            attrs={
                "accept": "image/*,video/*,.heic,.heif,image/heic,image/heif",
                "multiple": True,
            }
        ),
    )

    def clean_media_file(self):
        """Validate uploaded media (photo or video). Supports multiple files."""
        files = collect_media_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)


class SearchForm(forms.Form):
    """Reusable search form for list pages."""

    q = forms.CharField(
        label="",
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": "Search...", "class": "search-input"}
        ),
    )


class LogEntryQuickForm(StyledFormMixin, forms.Form):
    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())
    work_date = forms.DateTimeField(
        label="Date of work",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    submitter_name = forms.CharField(
        label="Maintainer name",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "enterkeyhint": "next",
                "autocomplete": "off",
                "data-1p-ignore": "true",
                "data-lpignore": "true",
                "placeholder": "Who did the work?",
            }
        ),
    )
    text = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What work was done?"}),
        max_length=1000,
    )
    media_file = MultiFileField(
        label="Photo",
        required=False,
        widget=MultiFileInput(
            attrs={
                "accept": "image/*,video/*,.heic,.heif,image/heic,image/heif",
                "multiple": True,
            }
        ),
    )

    def clean_work_date(self):
        """Validate that work_date is not in the future."""
        work_date = self.cleaned_data.get("work_date")
        if work_date:
            # Allow any time today, reject future dates
            today = timezone.localdate()
            if work_date.date() > today:
                raise forms.ValidationError("Date cannot be in the future.")
        return work_date

    def clean_media_file(self):
        """Validate uploaded media (photo or video). Supports multiple files."""
        files = collect_media_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)

    def clean_machine_slug(self):
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a machine.")
