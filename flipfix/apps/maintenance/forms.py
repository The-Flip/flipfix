"""Forms for maintenance workflows."""

from django import forms
from django.utils import timezone

from flipfix.apps.catalog.validators import clean_machine_slug
from flipfix.apps.core.forms import (
    MarkdownTextarea,
    MultiFileField,
    StyledFormMixin,
    clean_markdown_field,
    clean_media_files,
    clean_occurred_at_or_now,
)
from flipfix.apps.core.markdown_links import sync_references
from flipfix.apps.maintenance.models import LogEntry, ProblemReport


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
        return clean_machine_slug(self.cleaned_data)

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

    media_file = MultiFileField(label="Photo", required=False)

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
        return clean_markdown_field(self.cleaned_data, "description")

    def clean_media_file(self):
        """Validate uploaded media (photo or video). Supports multiple files."""
        return clean_media_files(self.files, self.cleaned_data)

    def clean_occurred_at(self):
        """Default to now if occurred_at is empty."""
        return clean_occurred_at_or_now(self.cleaned_data)

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
    media_file = MultiFileField(label="Photo", required=False)

    def clean_text(self):
        """Convert authoring format links to storage format."""
        return clean_markdown_field(self.cleaned_data, "text")

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
        return clean_media_files(self.files, self.cleaned_data)

    def clean_machine_slug(self):
        return clean_machine_slug(self.cleaned_data)
