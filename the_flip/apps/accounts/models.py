"""Accounts domain models."""

import secrets

from django.conf import settings
from django.db import models

from the_flip.apps.core.models import TimeStampedMixin


class Maintainer(TimeStampedMixin):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_shared_account = models.BooleanField(
        default=False,
        help_text="Shared accounts are used on workshop terminals by multiple maintainers.",
    )

    class Meta:
        ordering = ["user__username"]
        permissions = [
            ("can_access_maintainer_portal", "Can access the maintainer portal"),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        full_name = self.user.get_full_name()
        return full_name or self.user.get_username()

    @classmethod
    def match_by_name(cls, name: str) -> "Maintainer | None":
        """Find a maintainer by username or full name (case-insensitive).

        Args:
            name: Username or full name to match.

        Returns:
            Matching Maintainer or None if not found.
        """
        normalized = name.lower().strip()
        if not normalized:
            return None
        for maintainer in cls.objects.select_related("user"):
            username = maintainer.user.username.lower()
            full_name = (maintainer.user.get_full_name() or "").lower()
            if normalized in {username, full_name}:
                return maintainer
        return None


def generate_invitation_token() -> str:
    """Generate a secure random token for invitations."""
    return secrets.token_urlsafe(32)


class Invitation(TimeStampedMixin):
    """Invitation for a new maintainer to register."""

    email = models.EmailField(unique=True)
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "used" if self.used else "pending"
        return f"{self.email} ({status})"
