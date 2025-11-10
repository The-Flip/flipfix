from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils.text import slugify


class MachineModel(models.Model):
    """
    A model of pinball machine.

    Represents the abstract machine type (manufacturer, year, technical specs),
    not specific instances of physical machines owned by the museum.
    """

    ERA_PM = "PM"
    ERA_EM = "EM"
    ERA_SS = "SS"

    ERA_CHOICES = [
        (ERA_PM, "Pure Mechanical"),
        (ERA_EM, "Electromechanical"),
        (ERA_SS, "Solid State"),
    ]

    name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Year of manufacture"
    )
    month = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month of manufacture (1-12)",
    )
    era = models.CharField(
        max_length=2,
        choices=ERA_CHOICES,
        blank=False,
        verbose_name="Era",
        help_text="Pure Mechanical, Electromechanical, or Solid State"
    )
    system = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., WPC, System 11, MPU-1"
    )
    scoring = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display type: manual, reels, 7-segment, DMD, video"
    )
    flipper_count = models.CharField(
        max_length=10,
        blank=True,
        validators=[RegexValidator(regex=r'^\d+$', message='Must be a number')],
        help_text="Number of flippers",
    )
    pinside_rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Pinside community rating",
    )
    ipdb_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="IPDB ID",
        help_text="Internet Pinball Machine Database ID number"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
        ordering = ['name']
        verbose_name = "Machine Model"
        verbose_name_plural = "Machine Models"

    def __str__(self):
        return self.name


class MachineInstanceQuerySet(models.QuerySet):
    def on_floor(self):
        return self.filter(location=MachineInstance.LOCATION_FLOOR)

    def in_workshop(self):
        return self.filter(location=MachineInstance.LOCATION_WORKSHOP)

    def in_storage(self):
        return self.filter(location=MachineInstance.LOCATION_STORAGE)

    def by_name(self, name):
        """Filter by display name (checks both name_override and model__name)."""
        from django.db.models import Q
        return self.filter(Q(name_override=name) | Q(model__name=name))


def generate_unique_slug(instance):
    """
    Generate a unique slug for use in URLs for a MachineInstance.
    """
    base_name = instance.name  # Uses @property
    slug = slugify(base_name)

    unique_slug = slug
    counter = 2

    while MachineInstance.objects.filter(slug=unique_slug).exclude(pk=instance.pk).exists():
        unique_slug = f"{slug}-{counter}"
        counter += 1

    return unique_slug


class MachineInstance(models.Model):
    """
    A specific physical pinball machine owned by the museum.
    """

    OPERATIONAL_STATUS_GOOD = "good"
    OPERATIONAL_STATUS_UNKNOWN = "unknown"
    OPERATIONAL_STATUS_FIXING = "fixing"
    OPERATIONAL_STATUS_BROKEN = "broken"

    OPERATIONAL_STATUS_CHOICES = [
        (OPERATIONAL_STATUS_GOOD, "Good"),
        (OPERATIONAL_STATUS_UNKNOWN, "Unknown"),
        (OPERATIONAL_STATUS_FIXING, "Fixing"),
        (OPERATIONAL_STATUS_BROKEN, "Broken"),
    ]

    LOCATION_FLOOR = "floor"
    LOCATION_STORAGE = "storage"
    LOCATION_WORKSHOP = "workshop"

    LOCATION_CHOICES = [
        (LOCATION_FLOOR, "Floor"),
        (LOCATION_STORAGE, "Storage"),
        (LOCATION_WORKSHOP, "Workshop"),
    ]

    # Relationship
    model = models.ForeignKey(
        MachineModel,
        on_delete=models.PROTECT,
        related_name='instances',
        verbose_name="Machine model"
    )

    # Identity
    slug = models.SlugField(
        unique=True,
        max_length=200,
        help_text="URL-friendly identifier, auto-generated from name"
    )
    name_override = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Name override",
        help_text="Optional custom name. Leave blank to use the machine model's name."
    )

    # Physical identification
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Serial number from manufacturer"
    )

    # Acquisition tracking
    acquisition_notes = models.TextField(
        blank=True,
        help_text="Story of the acquisition, date acquired, source, price, initial condition etc"
    )

    # Location & status
    location = models.CharField(
        max_length=20,
        choices=LOCATION_CHOICES,
        blank=True,
        help_text="Physical location"
    )
    operational_status = models.CharField(
        max_length=20,
        choices=OPERATIONAL_STATUS_CHOICES,
        default=OPERATIONAL_STATUS_UNKNOWN,
        db_index=True,
        verbose_name="Status",
        help_text="Current operational condition"
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
        ordering = ['model__name', 'serial_number']
        verbose_name = "Machine Instance"
        verbose_name_plural = "Machine Instances"

    @property
    def name(self):
        """
        Display name for this machine.
        """
        return self.name_override or self.model.name

    def save(self, *args, **kwargs):
        # Auto-generate slug if not set
        if not self.slug:
            self.slug = generate_unique_slug(self)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Maintainer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class ProblemReportQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=ProblemReport.STATUS_OPEN)

    def closed(self):
        return self.filter(status=ProblemReport.STATUS_CLOSED)


class ProblemReport(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    PROBLEM_STUCK_BALL = "stuck_ball"
    PROBLEM_NO_CREDITS = "no_credits"
    PROBLEM_OTHER = "other"

    PROBLEM_TYPE_CHOICES = [
        (PROBLEM_STUCK_BALL, "Stuck Ball"),
        (PROBLEM_NO_CREDITS, "No Credits"),
        (PROBLEM_OTHER, "Other"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    machine = models.ForeignKey(MachineInstance, on_delete=models.CASCADE, related_name="reports")

    # Denormalized current status, for easy querying
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )

    # Who reported it: either logged-in user or anonymous visitor info
    reported_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="problem_reports_created",
    )
    reported_by_name = models.CharField(max_length=200, blank=True)
    reported_by_contact = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional email/phone in case we want to follow up.",
    )
    device_info = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, protocol='both')

    problem_type = models.CharField(
        max_length=50,
        choices=PROBLEM_TYPE_CHOICES,
        default=PROBLEM_OTHER,
        db_index=True,
    )
    problem_text = models.TextField(blank=True)

    objects = ProblemReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Problem Report"
        verbose_name_plural = "Problem Reports"

    def __str__(self):
        return f"{self.machine.name} – {self.get_problem_type_display()}"

    def add_note(self, maintainer: "Maintainer | None", text: str):
        """
        Convenience method to append a note to this report.
        Does NOT change status.
        """
        return ReportUpdate.objects.create(
            report=self,
            maintainer=maintainer,
            text=text,
        )

    def set_status(self, status: str, maintainer: "Maintainer | None", text: str = ""):
        """
        Change the report's current status AND record that change
        in the update history.
        """
        if status not in dict(self.STATUS_CHOICES):
            raise ValueError(f"Invalid status: {status}")

        old_status = self.status
        if old_status == status and not text:
            # Nothing to do; you could relax this if you want to always log.
            return None

        self.status = status
        self.save(update_fields=["status"])

        return ReportUpdate.objects.create(
            report=self,
            maintainer=maintainer,
            status=status,
            text=text,
        )

    def set_machine_status(self, machine_status: str, maintainer: "Maintainer | None", text: str = ""):
        """
        Change the machine's status AND record that change
        in the update history. Also automatically updates the report status:
        - Machine status 'good' -> closes the report
        - Machine status 'broken' or 'fixing' -> opens the report
        """
        if machine_status not in dict(MachineInstance.OPERATIONAL_STATUS_CHOICES):
            raise ValueError(f"Invalid machine status: {machine_status}")

        old_machine_status = self.machine.operational_status
        if old_machine_status == machine_status and not text:
            # Nothing to do
            return None

        self.machine.operational_status = machine_status
        self.machine.save(update_fields=["operational_status"])

        # Automatically update report status based on machine status
        new_report_status = None
        if machine_status == MachineInstance.OPERATIONAL_STATUS_GOOD:
            new_report_status = self.STATUS_CLOSED
        elif machine_status in (MachineInstance.OPERATIONAL_STATUS_BROKEN, MachineInstance.OPERATIONAL_STATUS_FIXING):
            new_report_status = self.STATUS_OPEN

        # Update report status if it changed
        if new_report_status and self.status != new_report_status:
            self.status = new_report_status
            self.save(update_fields=["status"])

        return ReportUpdate.objects.create(
            report=self,
            maintainer=maintainer,
            machine_status=machine_status,
            status=new_report_status if new_report_status else None,
            text=text,
        )


class ReportUpdate(models.Model):
    report = models.ForeignKey(
        ProblemReport,
        on_delete=models.CASCADE,
        related_name="updates",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    maintainer = models.ForeignKey(
        Maintainer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Human text: what was done / observed
    text = models.TextField(blank=True)

    # If set, this update *also* changed status.
    # If null, this update is just a note.
    status = models.CharField(
        max_length=20,
        choices=ProblemReport.STATUS_CHOICES,
        null=True,
        blank=True,
    )

    # If set, this update *also* changed the machine's status.
    # If null, the machine status was not changed.
    machine_status = models.CharField(
        max_length=20,
        choices=MachineInstance.OPERATIONAL_STATUS_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Problem Report Update"
        verbose_name_plural = "Problem Report Updates"

    def __str__(self):
        label = f"Update on report {self.report_id}"
        if self.status:
            label += f" → {self.status}"
        return label
