"""Wiki domain models."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from the_flip.apps.core.models import TimeStampedMixin


class WikiPageQuerySet(models.QuerySet):
    """Custom queryset for WikiPage."""

    def search(self, query: str = ""):
        """Full-text search across title, slug, content, and tags.

        Returns empty queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self.none()

        return self.filter(
            models.Q(title__icontains=query)
            | models.Q(slug__icontains=query)
            | models.Q(content__icontains=query)
            | models.Q(tags__tag__icontains=query)
        ).distinct()


class WikiPage(TimeStampedMixin):
    """The actual content of a wiki page."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    content = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = WikiPageQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        """Sync slug to WikiPageTag records when slug changes."""
        # Detect slug change
        if self.pk:
            old_slug = WikiPage.objects.filter(pk=self.pk).values_list("slug", flat=True).first()
            slug_changed = old_slug and old_slug != self.slug
        else:
            slug_changed = False

        if slug_changed:
            # Check for collisions in ALL tags this page appears in
            page_tags = self.tags.values_list("tag", flat=True)
            collision = (
                WikiPageTag.objects.filter(tag__in=page_tags, slug=self.slug)
                .exclude(page=self)
                .exists()
            )

            if collision:
                raise ValidationError(
                    f"Slug '{self.slug}' already exists in one of this page's tags"
                )

        with transaction.atomic():
            super().save(*args, **kwargs)
            if slug_changed:
                self.tags.update(slug=self.slug)


# Sentinel value for untagged pages in WikiPageTag.tag
UNTAGGED_SENTINEL = ""


class WikiPageTag(models.Model):
    """Tags that place a wiki page in the navigation tree.

    A page can have multiple tags, appearing in multiple locations.
    Pages without explicit tags get an ``UNTAGGED_SENTINEL`` tag so they
    still appear in navigation and have a valid URL path.
    """

    page = models.ForeignKey(WikiPage, on_delete=models.CASCADE, related_name="tags")
    tag = models.CharField(
        max_length=500,
        blank=True,
        help_text='Slugified tag path, e.g., "machines/blackout"; empty = untagged',
    )
    slug = models.SlugField(
        max_length=200, help_text="Denormalized from page.slug for uniqueness constraint"
    )
    order = models.PositiveIntegerField(
        null=True, blank=True, help_text="Explicit order within tag; null = unordered"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["page", "tag"], name="wikipagetag_unique_page_tag"),
            models.UniqueConstraint(fields=["tag", "slug"], name="wikipagetag_unique_tag_slug"),
        ]
        ordering = [F("order").asc(nulls_last=True), "page__title"]

    def __str__(self) -> str:
        if self.tag:
            return f"{self.tag}/{self.slug}"
        return self.slug

    def save(self, *args, **kwargs):
        """Normalize tag path to slugified lowercase."""
        if self.tag:
            # Slugify each segment of the tag path
            segments = [slugify(s) for s in self.tag.split("/") if s.strip()]
            self.tag = "/".join(segments)
        super().save(*args, **kwargs)


class WikiTagOrder(models.Model):
    """Optional explicit ordering for tags in navigation.

    Tags without entries sort alphabetically.
    """

    tag = models.CharField(
        max_length=500,
        unique=True,
        help_text='Slugified tag path, e.g., "machines/blackout"',
    )
    order = models.PositiveIntegerField(help_text="Explicit order for this tag")

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.tag} (order={self.order})"


class TemplateOptionIndex(models.Model):
    """Index of wiki template options for create-form dropdowns.

    Auto-maintained from ``template:action`` markers where ``action``
    contains "option".  Rows are rebuilt on every wiki page save by
    ``sync_template_option_index()``.  Never edited manually.
    """

    page = models.ForeignKey(
        WikiPage, on_delete=models.CASCADE, related_name="template_option_index"
    )
    template_name = models.CharField(max_length=200)
    record_type = models.CharField(max_length=50, db_index=True)
    machine_slug = models.CharField(max_length=200, blank=True)
    location_slug = models.CharField(max_length=200, blank=True)
    priority = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=200)

    class Meta:
        unique_together = [("page", "template_name")]
        indexes = [
            models.Index(fields=["record_type", "priority", "machine_slug", "location_slug"]),
        ]
        ordering = ["label"]

    def __str__(self) -> str:
        return f"{self.label} ({self.record_type})"
