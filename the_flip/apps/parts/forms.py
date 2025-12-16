"""Forms for parts management."""

from django import forms

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import (
    StyledFormMixin,
    collect_media_files,
    validate_media_files,
)
from the_flip.apps.maintenance.forms import MultiFileField, MultiFileInput
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

    class Meta:
        model = PartRequest
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Describe what part is needed and why..."}
            ),
        }
        labels = {
            "text": "Description",
        }

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
        files = collect_media_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)


class PartRequestUpdateForm(StyledFormMixin, forms.ModelForm):
    """Form for creating an update/comment on a part request."""

    requester_name = forms.CharField(
        label="Who is posting this?",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search users..."}),
    )
    new_status = forms.ChoiceField(
        label="Change status to",
        choices=[("", "No change")] + list(PartRequest.STATUS_CHOICES),
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

    class Meta:
        model = PartRequestUpdate
        fields = ["text", "new_status"]
        widgets = {
            "text": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Add a comment or status update..."}
            ),
        }
        labels = {
            "text": "Comment",
        }

    def clean_media_file(self):
        """Validate uploaded media files."""
        files = collect_media_files(self.files, "media_file", self.cleaned_data)
        return validate_media_files(files)
