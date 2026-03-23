"""OAuth2 provider models for app-scoped capabilities."""

from django.conf import settings
from django.db import models

from flipfix.apps.core.models import TimeStampedMixin


class AppCapability(TimeStampedMixin):
    """A capability that an OAuth application defines and users can be granted."""

    app = models.ForeignKey(
        "oauth2_provider.Application",
        on_delete=models.CASCADE,
        related_name="capabilities",
    )
    slug = models.SlugField(
        max_length=100,
        help_text="Machine-readable identifier (e.g., 'control_power')",
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable name (e.g., 'Control Machine Power')",
    )
    description = models.TextField(
        blank=True,
        help_text="Explanation of what this capability allows",
    )

    class Meta:
        verbose_name_plural = "app capabilities"
        constraints = [
            models.UniqueConstraint(fields=["app", "slug"], name="unique_capability_per_app"),
        ]
        ordering = ["app", "name"]

    def __str__(self) -> str:
        return f"{self.app.name}: {self.name}"


class AppCapabilityGrant(TimeStampedMixin):
    """Grant of an app capability to a specific user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )
    capability = models.ForeignKey(
        AppCapability,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "capability"], name="unique_grant_per_user"),
        ]
        ordering = ["capability__app", "capability__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.capability}"
