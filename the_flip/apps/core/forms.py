"""Core form utilities and mixins."""

from pathlib import Path
from typing import Any

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.urls import reverse_lazy
from PIL import Image, UnidentifiedImageError

from the_flip.apps.core.media import (
    ALLOWED_HEIC_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    MAX_MEDIA_FILE_SIZE_BYTES,
)

# Widget type to CSS class mapping
WIDGET_CSS_CLASSES = {
    forms.TextInput: "form-input",
    forms.EmailInput: "form-input",
    forms.PasswordInput: "form-input",
    forms.NumberInput: "form-input",
    forms.URLInput: "form-input",
    forms.DateInput: "form-input",
    forms.DateTimeInput: "form-input",
    forms.TimeInput: "form-input",
    forms.Textarea: "form-input form-textarea",
    forms.Select: "form-input",
    forms.SelectMultiple: "form-input",
    forms.CheckboxInput: "checkbox",
    # File inputs and RadioSelect are handled separately in templates
}


class MarkdownTextarea(forms.Textarea):
    """Textarea pre-configured for markdown editing.

    Provides the data attributes needed by link_autocomplete.js and
    markdown_shortcuts.js. Forms using this widget only need to specify
    per-field attrs like ``rows`` or ``placeholder``.

    Templates must include the companion scripts partial::

        {% include "core/partials/markdown_textarea_scripts.html" %}
    """

    def __init__(self, attrs=None):
        defaults = {
            "data-text-textarea": "",
            "data-link-autocomplete": "",
            "data-link-api-url": reverse_lazy("api-link-targets"),
            "data-markdown-shortcuts": "",
        }
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)


class StyledFormMixin:
    """
    Mixin that adds CSS classes to form widgets automatically.

    Apply to form classes to enable use of {{ field }} in templates
    while maintaining consistent styling.

    Usage:
        class MyForm(StyledFormMixin, forms.Form):
            name = forms.CharField()

    The mixin preserves any existing widget attrs and only adds
    the CSS class if not already present.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()

    def _apply_widget_classes(self):
        """Apply CSS classes to all field widgets based on widget type."""
        for field in self.fields.values():
            widget = field.widget
            for widget_type, css_class in WIDGET_CSS_CLASSES.items():
                if isinstance(widget, widget_type):
                    existing = widget.attrs.get("class", "")
                    # Check for exact class match (word boundary), not substring
                    existing_classes = existing.split()
                    for cls in css_class.split():
                        if cls not in existing_classes:
                            existing_classes.append(cls)
                    widget.attrs["class"] = " ".join(existing_classes)
                    break


def validate_media_files(files: list[UploadedFile]) -> list[UploadedFile]:
    """Validate uploaded media files (photos or videos).

    Args:
        files: List of uploaded files to validate.

    Returns:
        List of validated files.

    Raises:
        forms.ValidationError: If any file fails validation.
    """
    if not files:
        return []

    cleaned_files = []

    for media in files:
        if media.size and media.size > MAX_MEDIA_FILE_SIZE_BYTES:
            raise forms.ValidationError("File too large. Maximum size is 200MB.")

        content_type = (getattr(media, "content_type", "") or "").lower()
        ext = Path(getattr(media, "name", "")).suffix.lower()

        # Videos pass through without image verification
        if content_type.startswith("video/") or ext in ALLOWED_VIDEO_EXTENSIONS:
            cleaned_files.append(media)
            continue

        # Reject non-image content types (except HEIC which browsers may not recognize)
        if (
            content_type
            and not content_type.startswith("image/")
            and ext not in ALLOWED_HEIC_EXTENSIONS
        ):
            raise forms.ValidationError("Upload a valid image or video.")

        # Verify image can be opened by PIL
        try:
            media.seek(0)
        except (OSError, AttributeError):
            pass

        try:
            Image.open(media).verify()
        except (UnidentifiedImageError, OSError) as err:
            raise forms.ValidationError("Upload a valid image or video.") from err
        finally:
            try:
                media.seek(0)
            except (OSError, AttributeError):
                pass

        cleaned_files.append(media)

    return cleaned_files


def normalize_uploaded_files(
    files_dict: Any, field_name: str, cleaned_data: dict
) -> list[UploadedFile]:
    """Collect uploaded files from both multi-file and single-file contexts.

    Handles the complexity of file uploads coming from different sources:
    - Multi-file uploads via getlist()
    - Single file uploads in tests
    - Lists/tuples passed directly

    Args:
        files_dict: The request.FILES or similar object.
        field_name: Name of the file field.
        cleaned_data: The form's cleaned_data dict.

    Returns:
        List of uploaded files.
    """
    files = []

    # Try multi-file upload first
    if hasattr(files_dict, "getlist"):
        files = list(files_dict.getlist(field_name))

    # Fallback for single-file contexts (e.g., tests passing a simple dict)
    if not files:
        single = cleaned_data.get(field_name)
        if single:
            if isinstance(single, list | tuple):
                files = list(single)
            else:
                files = [single]

    return files
