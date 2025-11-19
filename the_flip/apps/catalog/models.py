"""Catalog models for machine metadata."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from the_flip.apps.core.models import TimeStampedModel


class MachineModel(TimeStampedModel):
    """Represents a pinball machine model."""

    ERA_PM = "PM"
    ERA_EM = "EM"
    ERA_SS = "SS"
    ERA_CHOICES = [
        (ERA_PM, "Pure Mechanical"),
        (ERA_EM, "Electromechanical"),
        (ERA_SS, "Solid State"),
    ]

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Official name of the pinball machine model"
    )
    slug = models.SlugField(unique=True, max_length=200, blank=True)
    manufacturer = models.CharField(
        max_length=200,
        blank=True,
        help_text="Company that manufactured this machine (e.g., Bally, Williams, Stern)"
    )
    month = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month of manufacture (1-12)"
    )
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Year of manufacture"
    )
    era = models.CharField(
        max_length=2,
        choices=ERA_CHOICES,
        help_text="Technology era of the machine"
    )
    system = models.CharField(
        max_length=100,
        blank=True,
        help_text="Electronic system type (e.g., WPC-95, System 11)"
    )
    scoring = models.CharField(
        max_length=100,
        blank=True,
        help_text="Scoring system type (e.g., Reel, 5 Digit, 7 Digit)"
    )
    flipper_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Number of flippers on the machine"
    )
    pinside_rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rating from Pinside (0.00-10.00)"
    )
    ipdb_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="IPDB ID",
        help_text="Internet Pinball Database ID number"
    )
    production_quantity = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Number of units produced (e.g., ~50,000)"
    )
    factory_address = models.CharField(
        max_length=300,
        blank=True,
        help_text="Address where the machine was manufactured"
    )
    design_credit = models.CharField(
        max_length=200,
        blank=True,
        help_text="Designer(s) of the machine"
    )
    concept_and_design_credit = models.CharField(
        max_length=200,
        blank=True,
        help_text="Concept and design credit (if different from designer)"
    )
    art_credit = models.CharField(
        max_length=200,
        blank=True,
        help_text="Artist(s) who created the artwork"
    )
    sound_credit = models.CharField(
        max_length=200,
        blank=True,
        help_text="Sound designer(s) or composer(s)"
    )
    educational_text = models.TextField(
        blank=True,
        help_text="Educational description for museum visitors"
    )
    illustration_filename = models.CharField(
        max_length=255,
        blank=True,
        help_text="Filename of the illustration image"
    )
    sources_notes = models.TextField(
        blank=True,
        help_text="Notes about data sources and references"
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

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

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
    def visible(self):
        return self.select_related("model")


class MachineInstance(TimeStampedModel):
    """Physical machine owned by the museum."""

    LOCATION_FLOOR = "floor"
    LOCATION_WORKSHOP = "workshop"
    LOCATION_STORAGE = "storage"
    LOCATION_CHOICES = [
        (LOCATION_FLOOR, "Floor"),
        (LOCATION_WORKSHOP, "Workshop"),
        (LOCATION_STORAGE, "Storage"),
    ]

    STATUS_GOOD = "good"
    STATUS_UNKNOWN = "unknown"
    STATUS_FIXING = "fixing"
    STATUS_BROKEN = "broken"
    STATUS_CHOICES = [
        (STATUS_GOOD, "Good"),
        (STATUS_UNKNOWN, "Unknown"),
        (STATUS_FIXING, "Fixing"),
        (STATUS_BROKEN, "Broken"),
    ]

    model = models.ForeignKey(
        MachineModel,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    slug = models.SlugField(unique=True, blank=True)
    name_override = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Name Override",
        help_text="Give this machine a name other than the machine's model name"
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Serial Number",
        help_text="Serial number from manufacturer"
    )
    acquisition_notes = models.TextField(
        blank=True,
        verbose_name="Acquisition Notes",
        help_text="Details about acquisition history"
    )
    ownership_credit = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Ownership Credit",
        help_text="Credit for ownership"
    )
    location = models.CharField(
        max_length=20,
        choices=LOCATION_CHOICES,
        blank=True,
        help_text="Current physical location"
    )
    operational_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNKNOWN,
        verbose_name="Status",
        help_text="Current working condition"
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

    class Meta:
        ordering = ["model__name", "serial_number"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.name_override or self.model.name

    @property
    def ownership_display(self) -> str:
        return self.ownership_credit or "The Flip Collection"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("public-machine-detail", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.display_name) or "machine"
            slug = base_slug
            counter = 2
            while MachineInstance.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
