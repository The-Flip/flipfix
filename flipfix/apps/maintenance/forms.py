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
from flipfix.apps.maintenance.models import LogEntry, MaintenanceTaskType, ProblemReport


class ProblemReportForm(StyledFormMixin, forms.ModelForm):
    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())
    media_file = MultiFileField(label="Photo", required=False)

    class Meta:
        model = ProblemReport
        fields = ["description"]
        # Annotated with the base Widget type so subclasses can override with
        # other widget classes (e.g. the maintainer form's Select for priority).
        widgets: dict[str, forms.Widget] = {
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "stuck ball, sticky flipper, target not working...",
                }
            ),
        }
        labels = {
            "description": "What's wrong?",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A report must describe the problem: it's now the only substantive field.
        self.fields["description"].required = True

    def clean_machine_slug(self):
        return clean_machine_slug(self.cleaned_data)

    def clean_media_file(self):
        """Validate uploaded media (photos or video). Supports multiple files."""
        return clean_media_files(self.files, self.cleaned_data)


class MaintainerProblemReportForm(ProblemReportForm):
    """Extended problem report form for maintainers with media upload support.

    Unlike the public form, maintainers don't select a problem type - it defaults to "Other".
    Description is still required.
    """

    class Meta(ProblemReportForm.Meta):
        fields = ["description", "priority", "occurred_at"]
        # Annotated so the mixed widget types (Textarea + Select) share a base type.
        widgets: dict[str, forms.Widget] = {
            "description": MarkdownTextarea(
                attrs={"rows": 4, "placeholder": "Describe the problem..."}
            ),
            "priority": forms.Select(),
        }
        labels = {
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

    # media_file and clean_media_file are inherited from ProblemReportForm.

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
    """Form for editing a log entry's metadata (maintainer, timestamp, time spent)."""

    maintainer_name = forms.CharField(
        label="Who did the work?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )

    class Meta:
        model = LogEntry
        fields = ["occurred_at", "time_spent"]
        widgets = {
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
            "time_spent": forms.NumberInput(
                attrs={"step": "any", "min": "0", "class": "form-input form-input--no-spinner"}
            ),
        }
        labels = {
            "occurred_at": "When",
            "time_spent": "Time spent (hours)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["time_spent"].required = False

    def clean_time_spent(self):
        """Default to current value (or 0) when time_spent is omitted."""
        value = self.cleaned_data.get("time_spent")
        if value is None:
            return self.instance.time_spent if self.instance.pk else 0
        return value


class LogEntryQuickForm(StyledFormMixin, forms.Form):
    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())
    # Idempotency token: one value per rendered form (seeded in the view's
    # get_initial). Resubmitting the same rendered page carries the same token,
    # letting the view collapse duplicate submissions from a slow/retried
    # connection. Optional so a stale cached page without a token still works.
    submission_id = forms.UUIDField(required=False, widget=forms.HiddenInput())
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
    time_spent = forms.DecimalField(
        label="Time spent (hours)",
        max_digits=5,
        decimal_places=2,
        initial="0.0",
        required=False,
        min_value=0,
        help_text="Total person-hours for everyone involved",
        widget=forms.NumberInput(
            attrs={"step": "any", "min": "0", "class": "form-input--no-spinner"}
        ),
    )
    maintenance_tasks = forms.ModelMultipleChoiceField(
        label="Tasks performed",
        queryset=MaintenanceTaskType.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Recurring maintenance tasks completed during this work.",
    )

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
