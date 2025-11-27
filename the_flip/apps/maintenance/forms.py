"""Forms for maintenance workflows."""

from pathlib import Path

from django import forms
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.models import ProblemReport


class ProblemReportForm(forms.ModelForm):
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
        raise forms.ValidationError("Select a machine from the list.")


class SearchForm(forms.Form):
    """Reusable search form for list pages."""

    q = forms.CharField(
        label="",
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": "Search...", "class": "search-input"}
        ),
    )


class LogEntryQuickForm(forms.Form):
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
    media_file = forms.FileField(
        label="Photo",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/*,video/*,.heic,.heif,image/heic,image/heif"}
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
        """Validate uploaded media (photo or video)."""
        media = self.cleaned_data.get("media_file")
        if not media:
            return media

        max_size_bytes = 200 * 1024 * 1024
        if media.size and media.size > max_size_bytes:
            raise forms.ValidationError("File too large. Maximum size is 200MB.")

        content_type = (getattr(media, "content_type", "") or "").lower()
        ext = Path(getattr(media, "name", "")).suffix.lower()
        allowed_video_exts = {".mp4", ".mov", ".m4v", ".hevc"}

        if content_type.startswith("video/") or ext in allowed_video_exts:
            return media

        if content_type and not content_type.startswith("image/") and ext not in {".heic", ".heif"}:
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

        return media

    def clean_machine_slug(self):
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a machine from the list.")
