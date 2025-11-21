"""Forms for maintenance workflows."""
from pathlib import Path

from django import forms
from PIL import Image, UnidentifiedImageError

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
    photo = forms.FileField(
        label="Photo",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*,.heic,.heif,image/heic,image/heif"}),
    )

    def clean_photo(self):
        """Validate that the uploaded file is an image (including HEIC/HEIF)."""
        photo = self.cleaned_data.get("photo")
        if not photo:
            return photo

        content_type = getattr(photo, "content_type", "") or ""
        ext = Path(getattr(photo, "name", "")).suffix.lower()
        if content_type and not content_type.startswith("image/") and ext not in {".heic", ".heif"}:
            raise forms.ValidationError(
                "Upload a valid image. The file you uploaded was either not an image or was corrupted."
            )

        try:
            photo.seek(0)
        except Exception:
            pass

        try:
            Image.open(photo).verify()
        except (UnidentifiedImageError, OSError):
            raise forms.ValidationError(
                "Upload a valid image. The file you uploaded was either not an image or was corrupted."
            )
        finally:
            try:
                photo.seek(0)
            except Exception:
                pass

        return photo
