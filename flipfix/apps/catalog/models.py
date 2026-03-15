"""Catalog models for machine metadata."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils.text import slugify
from model_utils import FieldTracker
from simple_history.models import HistoricalRecords

from flipfix.apps.core.asset_ids import generate_asset_id
from flipfix.apps.core.models import TimeStampedMixin
from flipfix.apps.core.text import strip_leading_articles


class Location(models.Model):
    """Physical location where a machine can be placed."""

    name = models.CharField(max_length=100, unique=True, help_text="Display name for this location")
    slug = models.SlugField(
        max_length=100, unique=True, blank=True, help_text="URL-friendly identifier"
    )
    sort_order = models.PositiveIntegerField(
        default=0, help_text="Order in which locations appear in lists"
    )

    class Meta:
        verbose_name = "Machine location"
        verbose_name_plural = "Machine locations"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "location"
        super().save(*args, **kwargs)


class MachineModel(TimeStampedMixin):
    """Represents a pinball machine model."""

    class Era(models.TextChoices):
        """Technology era classification for pinball machines."""

        PM = "PM", "Pure Mechanical"
        EM = "EM", "Electromechanical"
        SS = "SS", "Solid State"

    name = models.CharField(
        max_length=200, unique=True, help_text="Official name of the pinball machine model"
    )
    slug = models.SlugField(unique=True, max_length=200, blank=True)
    manufacturer = models.CharField(
        max_length=200,
        blank=True,
        help_text="Company that manufactured this machine (e.g., Bally, Williams, Stern)",
    )
    month = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month of manufacture (1-12)",
    )
    year = models.PositiveIntegerField(null=True, blank=True, help_text="Year of manufacture")
    era = models.CharField(
        max_length=2, choices=Era.choices, blank=True, help_text="Technology era of the machine"
    )
    system = models.CharField(
        max_length=100, blank=True, help_text="Electronic system type (e.g., WPC-95, System 11)"
    )
    scoring = models.CharField(
        max_length=100, blank=True, help_text="Scoring system type (e.g., Reel, 5 Digit, 7 Digit)"
    )
    flipper_count = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Number of flippers on the machine"
    )
    pinside_rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rating from Pinside (0.00-10.00)",
    )
    ipdb_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="IPDB ID",
        help_text="Internet Pinball Database ID number",
    )
    production_quantity = models.CharField(
        max_length=50, null=True, blank=True, help_text="Number of units produced (e.g., ~50,000)"
    )
    factory_address = models.CharField(
        max_length=300, blank=True, help_text="Address where the machine was manufactured"
    )
    design_credit = models.CharField(
        max_length=200, blank=True, help_text="Designer(s) of the machine"
    )
    concept_and_design_credit = models.CharField(
        max_length=200,
        blank=True,
        help_text="Concept and design credit (if different from designer)",
    )
    art_credit = models.CharField(
        max_length=200, blank=True, help_text="Artist(s) who created the artwork"
    )
    sound_credit = models.CharField(
        max_length=200, blank=True, help_text="Sound designer(s) or composer(s)"
    )
    educational_text = models.TextField(
        blank=True, help_text="Educational description for museum visitors"
    )
    illustration_filename = models.CharField(
        max_length=255, blank=True, help_text="Filename of the illustration image"
    )
    sources_notes = models.TextField(
        blank=True, help_text="Notes about data sources and references"
    )
    sort_name = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="Name with leading articles stripped, for alphabetical sorting",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machine_models_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machine_models_updated",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_name"]

    def __str__(self) -> str:
        return self.name

    def get_admin_history_url(self) -> str:
        """Return URL to this model's Django admin change history."""
        return reverse("admin:catalog_machinemodel_history", args=[self.pk])

    def save(self, *args, **kwargs):
        self.sort_name = strip_leading_articles(self.name)
        if not self.slug:
            base_slug = slugify(self.name) or "model"
            slug = base_slug
            counter = 2
            while MachineModel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Owner(TimeStampedMixin):
    """Person or company that owns one or more pinball machines."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(unique=True, max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    alternate_contact = models.TextField(blank=True, help_text="Additional contact information")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owners_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owners_updated",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("owner-detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "owner"
            slug = base_slug
            counter = 2
            while Owner.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


OWNER_DOCUMENT_ALLOWED_EXTENSIONS = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"})


def owner_document_upload_to(instance: OwnerDocument, filename: str) -> str:
    """Generate upload path for owner documents."""
    return f"owner_documents/{instance.owner_id}/{uuid4()}-{filename}"


class OwnerDocument(TimeStampedMixin):
    """File attachment (PDF, image) associated with an owner."""

    owner = models.ForeignKey(Owner, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(
        max_length=200, blank=True, help_text="Optional. Filename used if blank."
    )
    file = models.FileField(upload_to=owner_document_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """Return title if set, otherwise the filename."""
        if self.title:
            return self.title
        if self.file:
            return Path(self.file.name).name
        return "Untitled document"

    @property
    def is_image(self) -> bool:
        """Return True if the file is an image (by extension)."""
        if not self.file:
            return False
        ext = Path(self.file.name).suffix.lower()
        return ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    @property
    def is_pdf(self) -> bool:
        """Return True if the file is a PDF."""
        if not self.file:
            return False
        return Path(self.file.name).suffix.lower() == ".pdf"


class MachineInstanceQuerySet(models.QuerySet):
    """Custom queryset for MachineInstance with common filters."""

    def visible(self):
        """Return machines with related model, location, and owner pre-fetched."""
        return self.select_related("model", "location", "owner")

    def active_for_matching(self):
        """Return machines suitable for Discord message matching.

        Includes machines with active operational statuses.
        """
        return self.select_related("model").filter(
            operational_status__in=[
                MachineInstance.OperationalStatus.GOOD,
                MachineInstance.OperationalStatus.FIXING,
                MachineInstance.OperationalStatus.BROKEN,
                MachineInstance.OperationalStatus.UNKNOWN,
            ]
        )


class MachineInstance(TimeStampedMixin):
    """Physical machine owned by the museum."""

    class OperationalStatus(models.TextChoices):
        """Current working condition of a physical machine."""

        GOOD = "good", "Good"
        FIXING = "fixing", "Fixing"
        BROKEN = "broken", "Broken"
        UNKNOWN = "unknown", "Unknown"

    asset_id = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        verbose_name="Asset ID",
        help_text="Unique asset identifier (e.g., M0001). Auto-generated.",
    )
    model = models.ForeignKey(
        MachineModel,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    slug = models.SlugField(unique=True, blank=True)
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this machine",
    )
    short_name = models.CharField(
        max_length=30,
        blank=True,
        unique=True,
        null=True,
        verbose_name="Short Name",
        help_text="Short name for notifications and mobile (e.g., 'Eight Ball 2')",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Serial Number",
        help_text="Serial number from manufacturer",
    )
    acquisition_notes = models.TextField(
        blank=True, verbose_name="Acquisition Notes", help_text="Details about acquisition history"
    )
    owner = models.ForeignKey(
        Owner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machines",
        help_text="Person or company that owns this machine",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="machines",
        help_text="Current physical location",
    )
    operational_status = models.CharField(
        max_length=20,
        choices=OperationalStatus.choices,
        default=OperationalStatus.UNKNOWN,
        verbose_name="Status",
        help_text="Current working condition",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machine_instances_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machine_instances_updated",
    )

    objects = MachineInstanceQuerySet.as_manager()
    history = HistoricalRecords()
    tracker = FieldTracker(fields=["operational_status", "location_id"])

    class Meta:
        ordering = ["model__sort_name", "serial_number"]

    def __str__(self) -> str:
        return self.name

    @property
    def short_display_name(self) -> str:
        """Return short_name if set, otherwise name."""
        return self.short_name or self.name

    @property
    def ownership_display(self) -> str:
        """Return owner name or default collection name."""
        if self.owner_id and self.owner:
            return self.owner.name
        return "The Flip Collection"

    def get_absolute_url(self):
        """Return the public-facing URL for this machine."""
        return reverse("public-machine-detail", args=[self.slug])

    def get_admin_history_url(self) -> str:
        """Return URL to this instance's Django admin change history."""
        return reverse("admin:catalog_machineinstance_history", args=[self.pk])

    def clean(self):
        """Validate name and short_name uniqueness with friendly error messages."""
        super().clean()
        if self.name:
            self.name = self.name.strip()
        # After stripping, check if name is empty (whitespace-only input)
        if not self.name:
            raise ValidationError({"name": "This field is required."})
        if MachineInstance.objects.filter(name__iexact=self.name).exclude(pk=self.pk).exists():
            raise ValidationError({"name": "A machine with this name already exists."})

        if self.short_name:
            self.short_name = self.short_name.strip()
            if not self.short_name:
                self.short_name = None
            elif (
                MachineInstance.objects.filter(short_name=self.short_name)
                .exclude(pk=self.pk)
                .exists()
            ):
                raise ValidationError(
                    {"short_name": "A machine with this short name already exists."}
                )

    ASSET_ID_PREFIX = "M"
    ASSET_ID_MAX_RETRIES = 3

    def save(self, *args, **kwargs):
        # Strip name and normalize short_name
        if self.name:
            self.name = self.name.strip()
        if self.short_name is not None:
            self.short_name = self.short_name.strip() or None
        if not self.slug:
            base_slug = slugify(self.name) or "machine"
            slug = base_slug
            counter = 2
            while MachineInstance.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if not self.asset_id:
            for attempt in range(self.ASSET_ID_MAX_RETRIES):
                self.asset_id = generate_asset_id(self.ASSET_ID_PREFIX, MachineInstance)
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    if attempt == self.ASSET_ID_MAX_RETRIES - 1:
                        raise
                    self.asset_id = ""  # Reset and retry
        else:
            super().save(*args, **kwargs)
