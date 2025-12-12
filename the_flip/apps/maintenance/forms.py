"""Forms for maintenance workflows."""

from pathlib import Path

from django import forms
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.forms import StyledFormMixin
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
        files = []
        if hasattr(self.files, "getlist"):
            files = list(self.files.getlist("media_file"))
        # Fallback for single-file contexts (e.g., tests passing a simple dict)
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

    def clean_machine_slug(self):
        slug = (self.cleaned_data.get("machine_slug") or "").strip()
        if not slug:
            return ""
        if MachineInstance.objects.filter(slug=slug).exists():
            return slug
        raise forms.ValidationError("Select a machine.")
