from django.db import models
from django.conf import settings


class Game(models.Model):
    TYPE_MECHANICAL = "M"
    TYPE_EM = "EM"
    TYPE_SS = "SS"
    TYPE_DMD = "DMD"
    TYPE_LCD = "LCD"

    TYPE_CHOICES = [
        (TYPE_MECHANICAL, "Mechanical"),
        (TYPE_EM, "Electro-Mechanical"),
        (TYPE_SS, "Solid State"),
        (TYPE_DMD, "Dot Matrix Display"),
        (TYPE_LCD, "LCD"),
    ]

    name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True, db_index=True,)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="games_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="games_updated",
    )

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
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="reports")

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

    def __str__(self):
        return f"{self.game.name} – {self.get_problem_type_display()}"

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

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        label = f"Update on report {self.report_id}"
        if self.status:
            label += f" → {self.status}"
        return label