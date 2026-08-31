"""Accounts domain models."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
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
            ("can_invite_users", "Can invite new users"),
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


#: How long a fresh invitation stays usable.
INVITATION_TTL = timedelta(days=14)

#: Cap on live, unaccepted invitations one person may hold at a time. Blunts a
#: compromised maintainer account minting registration links in bulk, without
#: getting in the way of a volunteer onboarding a few people in an evening.
MAX_OUTSTANDING_INVITES_PER_USER = 10


def generate_invitation_token() -> str:
    """Generate a secure random token for invitations."""
    return secrets.token_urlsafe(32)


def default_invitation_expiry() -> datetime:
    """Expiry stamped on a freshly created invitation."""
    return timezone.now() + INVITATION_TTL


class InvitationQuerySet(models.QuerySet):
    """Custom queryset for Invitation."""

    def pending(self) -> models.QuerySet:
        """Invitations that can still be accepted.

        Single source of truth for "open" — every caller that means
        "still usable" must go through here rather than re-deriving the
        three conditions.
        """
        return self.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )

    def accepted(self) -> models.QuerySet:
        """Invitations that produced an account."""
        return self.filter(accepted_at__isnull=False)

    def sent_by(self, user) -> models.QuerySet:
        """Invitations ``user`` created."""
        return self.filter(invited_by=user)


class Invitation(TimeStampedMixin):
    """Invitation for a new maintainer to register.

    Two deliberate design choices, both of which look like bugs if you
    don't know why they're there:

    **``email`` is not unique.** The rule we actually want is "at most one
    *open* invitation per address", and openness depends on ``expires_at``
    relative to now — which a partial unique index can't express without a
    stored status column, and a stored status column is exactly the drift
    the derived :attr:`status` avoids. The invite-create view instead looks
    for an existing :meth:`InvitationQuerySet.pending` invitation for the
    address and re-sends that one. Two racing creates at worst produce two
    valid links to the same person, which is harmless. Do not "fix" this
    back to ``unique=True``: it makes re-inviting somebody raise
    IntegrityError, which is what it used to do.

    **``token`` is stored in the clear**, unlike a password-reset token.
    The invite page shows the link with a copy button so a maintainer can
    hand it over in person or paste it into Discord when email delivery
    fails, and that requires the link to be recoverable after creation.
    The exposure is a 14-day, single-use, self-service signup link.
    """

    class Status(models.TextChoices):
        """Display-only. Derived from the timestamps; never a DB column."""

        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token)
    # SET_NULL, not CASCADE: deleting a user must not silently erase the
    # audit trail of who they invited or who invited them.
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
        help_text="Who sent this invitation. Null for invitations predating invite tracking.",
    )
    # The other half of the chain edge. OneToOne so ``user.invitation``
    # walks straight back to the inviter.
    accepted_by = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitation",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Indexed because pending() filters on it on every invite page load.
    expires_at = models.DateTimeField(default=default_invitation_expiry, db_index=True)
    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the invitation email was last sent. Null if it has never been sent.",
    )

    objects = InvitationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.status.value})"

    def get_absolute_url(self) -> str:
        return reverse("invite-detail", kwargs={"pk": self.pk})

    @property
    def status(self) -> Status:
        """Current state, derived from the timestamps.

        Order matters: a revoked invitation reads as revoked even if it
        has also expired, because revoking is the deliberate act and the
        one worth reporting.
        """
        if self.revoked_at is not None:
            return self.Status.REVOKED
        if self.accepted_at is not None:
            return self.Status.ACCEPTED
        if self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.Status.PENDING

    @property
    def status_label(self) -> str:
        """Human-readable status, for templates."""
        return self.Status(self.status).label

    @property
    def is_pending(self) -> bool:
        """Whether this invitation can still be accepted."""
        return self.status == self.Status.PENDING


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
