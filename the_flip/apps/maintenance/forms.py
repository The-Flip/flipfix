"""Forms for maintenance workflows."""

from django import forms
from django.utils import timezone

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import (
    MarkdownTextarea,
    StyledFormMixin,
    normalize_uploaded_files,
    validate_media_files,
)
from the_flip.apps.core.markdown_links import convert_authoring_to_storage, sync_references
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


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
        if problem_type == ProblemReport.ProblemType.OTHER and not description:
            self.add_error("description", "Please describe the problem.")
        return cleaned


class MaintainerProblemReportForm(ProblemReportForm):
    """Extended problem report form for maintainers with media upload support.

    Unlike the public form, maintainers don't select a problem type - it defaults to "Other".
    Description is still required.
    """

    class Meta(ProblemReportForm.Meta):
        fields = ["description", "priority", "occurred_at"]
        widgets = {
            **ProblemReportForm.Meta.widgets,
            "description": MarkdownTextarea(
                attrs={"rows": 4, "placeholder": "Describe the problem..."}
            ),
            "priority": forms.Select(),
        }
        labels = {
            **ProblemReportForm.Meta.labels,
            "description": "Description",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["priority"].choices = ProblemReport.Priority.maintainer_settable()

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

    # occurred_at is optional; model has default=timezone.now.
    # JS pre-fills client-side, but tests/API can omit it.
    occurred_at = forms.DateTimeField(
        label="When",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-input form-input--sm"}
        ),
    )

    def clean_description(self):
        """Convert authoring format links to storage format."""
        description = self.cleaned_data.get("description", "")
        if description:
            description = convert_authoring_to_storage(description)
        return description

    def clean_media_file(self):
        """Validate uploaded media (photo or video). Supports multiple files."""
        files = normalize_uploaded_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)

    def clean_occurred_at(self):
        """Default to now if occurred_at is empty.

        HTML forms submit empty strings for empty inputs, which Django interprets
        as 'field present but empty' rather than 'field absent'. Without this,
        the empty string becomes None and fails the model's NOT NULL constraint.
        """
        return self.cleaned_data.get("occurred_at") or timezone.now()

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            sync_references(instance, instance.description)
        return instance


class ProblemReportEditForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a problem report's metadata (reporter, timestamp)."""

    reporter_name = forms.CharField(
        label="Who reported this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )

    class Meta:
        model = ProblemReport
        fields = ["occurred_at"]
        widgets = {
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
        }
        labels = {
            "occurred_at": "When",
        }


class LogEntryEditForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a log entry's metadata (maintainer, timestamp)."""

    maintainer_name = forms.CharField(
        label="Who did the work?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )

    class Meta:
        model = LogEntry
        fields = ["occurred_at"]
        widgets = {
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
        }
        labels = {
            "occurred_at": "When",
        }


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
    occurred_at = forms.DateTimeField(
        label="Date of work",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    # submitter_name is no longer used - the chip input submits maintainer_usernames
    # and maintainer_freetext directly. Kept for backwards compatibility but optional.
    submitter_name = forms.CharField(
        label="Maintainer name",
        max_length=200,
        required=False,
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
        label="What work was done?",
        widget=MarkdownTextarea(attrs={"rows": 4, "placeholder": "Describe the work performed..."}),
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

    def clean_text(self):
        """Convert authoring format links to storage format."""
        text = self.cleaned_data.get("text", "")
        if text:
            text = convert_authoring_to_storage(text)
        return text

    def clean_occurred_at(self):
        """Validate that occurred_at is not in the future."""
        occurred_at = self.cleaned_data.get("occurred_at")
        if occurred_at:
            # Allow any time today, reject future dates
            today = timezone.localdate()
            if occurred_at.date() > today:
                raise forms.ValidationError("Date cannot be in the future.")
        return occurred_at

    def clean_media_file(self):
        """Validate uploaded media (photo or video). Supports multiple files."""
        files = normalize_uploaded_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)

    def clean_machine_slug(self):
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a machine.")
