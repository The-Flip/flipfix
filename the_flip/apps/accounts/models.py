"""Accounts domain models."""

import secrets

from django.conf import settings
from django.db import models

from the_flip.apps.core.models import TimeStampedModel


class Maintainer(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        full_name = self.user.get_full_name()
        return full_name or self.user.get_username()


def generate_invitation_token() -> str:
    """Generate a secure random token for invitations."""
    return secrets.token_urlsafe(32)


class Invitation(TimeStampedModel):
    """Invitation for a new maintainer to register."""

    email = models.EmailField(unique=True)
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "used" if self.used else "pending"
        return f"{self.email} ({status})"
