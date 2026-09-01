"""Invitation-based account creation."""

from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import InvitationRegistrationForm
from ..lifecycle import make_maintainer
from ..models import Invitation

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())

#: Why the link didn't work, phrased so the reader knows what to do next.
#: "Expired" must not read as "already used" — one means ask for another
#: link, the other means you already have an account.
UNUSABLE_INVITATION_MESSAGES = {
    Invitation.Status.ACCEPTED: ("This invitation has already been used. Try logging in instead."),
    Invitation.Status.REVOKED: (
        "This invitation was cancelled. Ask whoever invited you to send a new one."
    ),
    Invitation.Status.EXPIRED: (
        "This invitation has expired. Ask whoever invited you to send a new one."
    ),
}


def invitation_register(request, token):
    """Complete registration for an invited user."""
    invitation = get_object_or_404(Invitation, token=token)

    if not invitation.is_pending:
        messages.error(request, UNUSABLE_INVITATION_MESSAGES[invitation.status])
        return redirect("login")

    if request.method == "POST":
        form = InvitationRegistrationForm(request.POST)
        if form.is_valid():
            user = _register(form, invitation)
            if user is None:
                messages.error(
                    request,
                    "This invitation was just used from somewhere else. "
                    "Try logging in, or ask for a new invitation.",
                )
                return redirect("login")

            login(request, user)
            messages.success(request, "Welcome! Your account has been created.")
            return redirect("home")
    else:
        form = InvitationRegistrationForm(initial={"email": invitation.email})

    return render(
        request,
        "registration/invitation_register.html",
        {"form": form, "invitation": invitation},
    )


@transaction.atomic
def _register(form, invitation: Invitation):
    """Create the account and claim the invitation, or return ``None``.

    The claim is a conditional UPDATE rather than a ``select_for_update``
    because dev runs on SQLite, where Django's backend sets
    ``has_select_for_update = False`` and raises ``NotSupportedError``. A
    single UPDATE filtered on ``accepted_at__isnull=True`` is atomic on both
    backends: exactly one of two concurrent registrations gets a row count
    of 1, and the loser rolls the whole transaction back.
    """
    user = User.objects.create_user(
        username=form.cleaned_data["username"],
        email=form.cleaned_data["email"],
        password=form.cleaned_data["password"],
        first_name=form.cleaned_data.get("first_name", ""),
        last_name=form.cleaned_data.get("last_name", ""),
    )
    make_maintainer(user)

    claimed = Invitation.objects.filter(pk=invitation.pk, accepted_at__isnull=True).update(
        accepted_at=timezone.now(), accepted_by=user
    )
    if claimed != 1:
        transaction.set_rollback(True)
        return None
    return user
