"""Forms for parts management."""

from pathlib import Path

from django import forms
from PIL import Image, UnidentifiedImageError

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import StyledFormMixin
from the_flip.apps.maintenance.forms import MultiFileField, MultiFileInput
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


class PartRequestForm(StyledFormMixin, forms.ModelForm):
    """Form for creating or editing a part request."""

    machine_slug = forms.CharField(required=False, widget=forms.HiddenInput())
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
        files = []
        if hasattr(self.files, "getlist"):
            files = list(self.files.getlist("media_file"))
        if not files:
            single = self.cleaned_data.get("media_file")
            if single:
                if isinstance(single, list | tuple):
                    files = list(single)
                else:
                    files = [single]
        if not files:
            return []

        max_size_bytes = 200 * 1024 * 1024
        allowed_video_exts = {".mp4", ".mov", ".m4v", ".hevc"}
        cleaned_files = []

        for media in files:
            if media.size and media.size > max_size_bytes:
                raise forms.ValidationError("File too large. Maximum size is 200MB.")

            content_type = (getattr(media, "content_type", "") or "").lower()
            ext = Path(getattr(media, "name", "")).suffix.lower()

            if content_type.startswith("video/") or ext in allowed_video_exts:
                cleaned_files.append(media)
                continue

            if (
                content_type
                and not content_type.startswith("image/")
                and ext not in {".heic", ".heif"}
            ):
                raise forms.ValidationError("Upload a valid image or video.")

            try:
                media.seek(0)
            except Exception:
                pass

            try:
                Image.open(media).verify()
            except (UnidentifiedImageError, OSError):
                raise forms.ValidationError("Upload a valid image or video.")
            finally:
                try:
                    media.seek(0)
                except Exception:
                    pass

            cleaned_files.append(media)

        return cleaned_files


class PartRequestUpdateForm(StyledFormMixin, forms.ModelForm):
    """Form for creating an update/comment on a part request."""

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
        files = []
        if hasattr(self.files, "getlist"):
            files = list(self.files.getlist("media_file"))
        if not files:
            single = self.cleaned_data.get("media_file")
            if single:
                if isinstance(single, list | tuple):
                    files = list(single)
                else:
                    files = [single]
        if not files:
            return []

        max_size_bytes = 200 * 1024 * 1024
        allowed_video_exts = {".mp4", ".mov", ".m4v", ".hevc"}
        cleaned_files = []

        for media in files:
            if media.size and media.size > max_size_bytes:
                raise forms.ValidationError("File too large. Maximum size is 200MB.")

            content_type = (getattr(media, "content_type", "") or "").lower()
            ext = Path(getattr(media, "name", "")).suffix.lower()

            if content_type.startswith("video/") or ext in allowed_video_exts:
                cleaned_files.append(media)
                continue

            if (
                content_type
                and not content_type.startswith("image/")
                and ext not in {".heic", ".heif"}
            ):
                raise forms.ValidationError("Upload a valid image or video.")

            try:
                media.seek(0)
            except Exception:
                pass

            try:
                Image.open(media).verify()
            except (UnidentifiedImageError, OSError):
                raise forms.ValidationError("Upload a valid image or video.")
            finally:
                try:
                    media.seek(0)
                except Exception:
                    pass

            cleaned_files.append(media)

        return cleaned_files
