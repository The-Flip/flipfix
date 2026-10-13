"""Forms for wiki pages."""

from django import forms
from django.urls import reverse
from django.utils.text import slugify

from flipfix.apps.core.forms import MarkdownTextarea, StyledFormMixin, validate_media_files
from flipfix.apps.core.markdown_links import (
    convert_authoring_to_storage,
    convert_storage_to_authoring,
    sync_references,
)
from flipfix.apps.core.media import is_video_file

from .actions import sync_template_option_index, validate_template_syntax
from .media import MAX_WIKI_IMAGE_BYTES, record_media_references
from .models import UNTAGGED_SENTINEL, WikiPage, WikiPageTag


class WikiPageForm(StyledFormMixin, forms.ModelForm):
    """Form for creating and editing wiki pages."""

    class Meta:
        model = WikiPage
        fields = ["title", "content"]
        widgets = {
            "content": MarkdownTextarea(attrs={"rows": 20}),
        }

    def __init__(self, *args, tags=None, **kwargs):
        """Initialize form with optional tags list.

        Args:
            tags: List of tag strings from request.POST.getlist('tags')
        """
        super().__init__(*args, **kwargs)
        self._tags = tags or []

        # Configure inline image upload (markdown_image_upload.js). On the edit
        # page, uploads link to the page immediately.
        content_attrs = self.fields["content"].widget.attrs
        content_attrs["data-image-upload-url"] = reverse("api-wiki-media-upload")
        if self.instance.pk:
            content_attrs["data-image-upload-page"] = str(self.instance.pk)

        # Convert storage format to authoring format for editing
        if self.instance.pk and self.instance.content:
            self.initial["content"] = convert_storage_to_authoring(self.instance.content)

    def get_initial_tags(self) -> str:
        """Get comma-separated initial tags for the template component."""
        if self.instance.pk:
            tags = self.instance.tags.exclude(tag=UNTAGGED_SENTINEL).values_list("tag", flat=True)
            return ", ".join(tags)
        if self._tags:
            return ", ".join(self._tags)
        return ""

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        """Normalize a tag path: strip, slugify each segment, rejoin.

        Examples:
            "  Machines " -> "machines"
            "Machines/Stern" -> "machines/stern"
        """
        segments = [slugify(s) for s in tag.split("/") if s.strip()]
        return "/".join(segments)

    def clean_title(self):
        """Validate that the slug derived from the title won't collide."""
        title = self.cleaned_data.get("title", "")
        new_slug = slugify(title)
        if not new_slug:
            raise forms.ValidationError("Title must produce a valid slug.")

        # Determine which tags this page will have
        if self.instance.pk:
            current_tags = set(self.instance.tags.values_list("tag", flat=True))
        else:
            # New page will get the untagged sentinel at minimum
            current_tags = {UNTAGGED_SENTINEL}

        # Also include tags being submitted with the form
        for tag in self._tags:
            normalized = self._normalize_tag(tag)
            if normalized:
                current_tags.add(normalized)

        # Check for collision: another page's tag with same (tag, slug)
        collision_qs = WikiPageTag.objects.filter(tag__in=current_tags, slug=new_slug)
        if self.instance.pk:
            collision_qs = collision_qs.exclude(page=self.instance)

        if collision_qs.exists():
            raise forms.ValidationError(
                f"A page with the slug '{new_slug}' already exists in one of this page's tags."
            )

        return title

    def clean_content(self):
        """Convert authoring format links to storage format and validate template syntax.

        Raises ValidationError if linked targets don't exist or if template
        markers have structural/attribute errors.
        """
        content = self.cleaned_data.get("content", "")
        if content:
            # convert_authoring_to_storage raises ValidationError if links are broken
            content = convert_authoring_to_storage(content)
            # Validate template marker syntax
            template_errors = validate_template_syntax(content)
            if template_errors:
                raise forms.ValidationError(template_errors)
        return content

    def save(self, commit=True):
        """Save the page, update its tags, and sync link references."""
        # Auto-generate slug from title (on create and on rename)
        self.instance.slug = slugify(self.cleaned_data["title"])

        page = super().save(commit=commit)

        if commit:
            self._save_tags(page)
            # Sync reference tables based on links in content
            sync_references(page, page.content)
            record_media_references(page)
            # Rebuild template option index from template:action markers
            self.template_sync_result = sync_template_option_index(page)

        return page

    def _save_tags(self, page):
        """Sync WikiPageTag records with the tags list."""
        # Normalize tags (model's save() will also normalize, but we do it here for comparison)
        new_tags = set()
        for tag in self._tags:
            normalized = self._normalize_tag(tag)
            if normalized:
                new_tags.add(normalized)

        existing_tags = set(page.tags.values_list("tag", flat=True))

        # Remove the empty sentinel from comparison - it's auto-managed
        existing_tags.discard(UNTAGGED_SENTINEL)

        # Tags to add
        for tag in new_tags - existing_tags:
            WikiPageTag.objects.create(page=page, tag=tag, slug=page.slug)

        # Tags to remove
        tags_to_remove = existing_tags - new_tags
        if tags_to_remove:
            page.tags.filter(tag__in=tags_to_remove).delete()

        # If page now has no tags, ensure it has the untagged sentinel
        # (The post_save signal handles this, but we check just in case)
        if not page.tags.exists():
            WikiPageTag.objects.create(page=page, tag=UNTAGGED_SENTINEL, slug=page.slug)


class WikiMediaUploadForm(StyledFormMixin, forms.Form):
    """Validate an inline media upload from the wiki markdown editor (images only, so far)."""

    file = forms.FileField()
    page = forms.ModelChoiceField(queryset=WikiPage.objects.all(), required=False)

    def clean_file(self):
        """Accept photos only, within the wiki size cap."""
        upload = self.cleaned_data["file"]
        if is_video_file(upload):
            raise forms.ValidationError("Only images can be added to docs.")
        if upload.size > MAX_WIKI_IMAGE_BYTES:
            limit_mb = MAX_WIKI_IMAGE_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"Image too large. Maximum size is {limit_mb}MB.")
        try:
            validate_media_files([upload])
        except forms.ValidationError as err:
            # Size is checked above, so the only failure left is "not an image";
            # the shared message also mentions video, which docs don't accept.
            raise forms.ValidationError("Upload a valid image.") from err
        return upload
