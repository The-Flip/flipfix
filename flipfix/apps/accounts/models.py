"""Accounts domain models."""

from __future__ import annotations

import secrets
from uuid import uuid4

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from flipfix.apps.core.models import AbstractMedia, TimeStampedMixin

# Usernames reserved for sibling routes under /users/<username>/.
# Both registration forms reject these so future routes can't be shadowed
# by a literal username.
RESERVED_USERNAMES = frozenset(
    {
        "me",
        "search",
        "invite",
        "admin",
        "new",
        "edit",
        "delete",
        "settings",
    }
)


class MaintainerQuerySet(models.QuerySet):
    """Custom queryset for Maintainer model."""

    def in_user_directory(self) -> models.QuerySet:
        """Maintainers that appear in the user directory.

        Single source of truth for the visibility predicate: active user,
        member of the Maintainers group, not a shared terminal account.
        """
        return self.filter(
            user__is_active=True,
            user__groups__name="Maintainers",
            is_shared_account=False,
        )


class Maintainer(TimeStampedMixin):
    """Profile extending Django User for museum maintainers."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_shared_account = models.BooleanField(
        default=False,
        help_text="Shared accounts are used on workshop terminals by multiple maintainers.",
    )
    bio = models.TextField(blank=True)
    # Indexed because we sort the user directory by it and will filter on it
    # for the future inactive-account deactivation sweep. Don't drop the index
    # thinking it's unused.
    last_active_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Most recent authenticated request from this maintainer. Updated at most once per day.",
    )

    objects = MaintainerQuerySet.as_manager()

    class Meta:
        ordering = ["user__username"]
        permissions = [
            ("can_access_maintainer_portal", "Can access the maintainer portal"),
            ("can_manage_catalog", "Can manage catalog (create machines, print QR codes)"),
            ("can_view_user_profiles", "Can view the user directory and profile pages"),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """Return full name if available, otherwise username."""
        full_name = self.user.get_full_name()
        return full_name or self.user.get_username()

    @classmethod
    def match_by_name(cls, name: str) -> Maintainer | None:
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


def maintainer_media_upload_to(instance: MaintainerMedia, filename: str) -> str:
    """Generate upload path for maintainer profile media."""
    return f"maintainers/{instance.maintainer_id}/{uuid4()}-{filename}"


class MaintainerMedia(AbstractMedia):
    """Media files attached to a maintainer's profile."""

    MAX_ITEMS_PER_MAINTAINER = 10

    parent_field_name = "maintainer"

    maintainer = models.ForeignKey(
        Maintainer,
        on_delete=models.CASCADE,
        related_name="media",
    )
    file = models.FileField(upload_to=maintainer_media_upload_to)
    thumbnail_file = models.FileField(upload_to=maintainer_media_upload_to, blank=True, null=True)
    transcoded_file = models.FileField(upload_to=maintainer_media_upload_to, blank=True, null=True)
    poster_file = models.ImageField(upload_to=maintainer_media_upload_to, blank=True, null=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Maintainer media"
        verbose_name_plural = "Maintainer media"

    def save(self, *args, **kwargs):
        # Ensure display_order is always non-null on insert. AbstractMedia
        # leaves it nullable, and Postgres vs SQLite disagree on NULL ordering
        # (last vs first for ASC), so without this the directory tile order
        # would differ between dev and prod. Scoped to MaintainerMedia for now;
        # parts/maintenance can adopt the same pattern when they wire reorder.
        if self._state.adding and self.display_order is None:
            max_order = MaintainerMedia.objects.filter(maintainer=self.maintainer).aggregate(
                models.Max("display_order")
            )["display_order__max"]
            # Race: two concurrent inserts may both read the same max and end
            # up with the same display_order. Accepted for v1 (single-user
            # feature, AJAX serializes uploads); ties are broken by created_at
            # via Meta.ordering. Do not reach for select_for_update "for safety."
            self.display_order = 0 if max_order is None else max_order + 1
        super().save(*args, **kwargs)
