"""Catalog models for machine metadata."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from the_flip.apps.core.models import TimeStampedMixin

# Cache timeout for machine matching lookups (used by Discord bot)
MACHINE_MATCHING_CACHE_SECONDS = 300  # 5 minutes


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
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_admin_history_url(self) -> str:
        """Return URL to this model's Django admin change history."""
        return reverse("admin:catalog_machinemodel_history", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "model"
            slug = base_slug
            counter = 2
            while MachineModel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class MachineInstanceQuerySet(models.QuerySet):
    """Custom queryset for MachineInstance with common filters."""

    def visible(self):
        """Return machines with related model and location pre-fetched."""
        return self.select_related("model", "location")

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
    ownership_credit = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Ownership Credit",
        help_text="Credit for ownership",
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

    class Meta:
        ordering = ["model__name", "serial_number"]

    def __str__(self) -> str:
        return self.name

    @property
    def short_display_name(self) -> str:
        """Return short_name if set, otherwise name."""
        return self.short_name or self.name

    @property
    def ownership_display(self) -> str:
        """Return ownership credit or default collection name."""
        return self.ownership_credit or "The Flip Collection"

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
        super().save(*args, **kwargs)


def get_machines_for_matching() -> list[MachineInstance]:
    """Get list of machines for Discord message matching.

    Uses Django cache to avoid repeated database queries.
    Cache expires after 5 minutes, so new machines will be picked up.
    """
    from django.core.cache import cache

    cache_key = "machines_for_matching"
    machines = cache.get(cache_key)

    if machines is None:
        machines = list(MachineInstance.objects.active_for_matching())
        cache.set(cache_key, machines, timeout=MACHINE_MATCHING_CACHE_SECONDS)

    return machines
