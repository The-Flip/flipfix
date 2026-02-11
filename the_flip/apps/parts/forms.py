"""Forms for parts management."""

from django import forms
from django.utils import timezone

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import (
    MarkdownTextarea,
    MultiFileField,
    MultiFileInput,
    StyledFormMixin,
    normalize_uploaded_files,
    validate_media_files,
)
from the_flip.apps.core.markdown_links import convert_authoring_to_storage
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


class PartRequestForm(StyledFormMixin, forms.ModelForm):
    """Form for creating or editing a part request."""

    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())
    requester_name = forms.CharField(
        label="Who is requesting this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Who is requesting this?"}),
    )
    media_file = MultiFileField(
        label="Photos/Videos",
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

    class Meta:
        model = PartRequest
        fields = ["text", "occurred_at"]
        widgets = {
            "text": MarkdownTextarea(
                attrs={"rows": 4, "placeholder": "Describe what part is needed and why..."}
            ),
        }
        labels = {
            "text": "Description",
        }

    def clean_text(self):
        """Convert authoring format links to storage format."""
        text = self.cleaned_data.get("text", "")
        if text:
            text = convert_authoring_to_storage(text)
        return text

    def clean_machine_slug(self):
        """Validate machine_slug if provided."""
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a valid machine.")

    def clean_media_file(self):
        """Validate uploaded media files."""
        files = normalize_uploaded_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)

    def clean_occurred_at(self):
        """Default to now if occurred_at is empty."""
        return self.cleaned_data.get("occurred_at") or timezone.now()


class PartRequestUpdateForm(StyledFormMixin, forms.ModelForm):
    """Form for posting an update/comment on a part request."""

    poster_name = forms.CharField(
        label="Who is posting this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )
    new_status = forms.ChoiceField(
        label="Change status to",
        choices=[("", "No change")] + list(PartRequest.Status.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    media_file = MultiFileField(
        label="Photos/Videos",
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

    class Meta:
        model = PartRequestUpdate
        fields = ["text", "new_status", "occurred_at"]
        widgets = {
            "text": MarkdownTextarea(
                attrs={"rows": 3, "placeholder": "Add a comment or status update..."}
            ),
        }
        labels = {
            "text": "Comment",
        }

    def clean_text(self):
        """Convert authoring format links to storage format."""
        text = self.cleaned_data.get("text", "")
        if text:
            text = convert_authoring_to_storage(text)
        return text

    def clean_media_file(self):
        """Validate uploaded media files."""
        files = normalize_uploaded_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)

    def clean_occurred_at(self):
        """Default to now if occurred_at is empty."""
        return self.cleaned_data.get("occurred_at") or timezone.now()


class PartRequestUpdateEditForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a part request update's metadata (poster, timestamp)."""

    poster_name = forms.CharField(
        label="Who posted this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )

    class Meta:
        model = PartRequestUpdate
        fields = ["occurred_at"]
        widgets = {
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
        }
        labels = {
            "occurred_at": "When",
        }


class PartRequestEditForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a part request's metadata (requester, timestamp)."""

    requester_name = forms.CharField(
        label="Who requested this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )

    class Meta:
        model = PartRequest
        fields = ["occurred_at"]
        widgets = {
            "occurred_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
        }
        labels = {
            "occurred_at": "When",
        }
