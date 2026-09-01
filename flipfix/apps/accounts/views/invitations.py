"""Maintainer-facing invitations: create, share, resend, revoke, prune.

Authorization note: ``docs/Views.md`` puts access control on the route via
``access=``, and that is where the coarse gate lives (these are all default
maintainer routes, plus two superuser ones). ``access=`` has no level for
"maintainer *and* a named capability", so the finer check is layered in
``dispatch()`` — the same shape ``UserDirectoryView`` uses for
``can_view_user_profiles``. It is a mixin here only because five views need
it; one more copy of the same three lines would be worse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from ..emails import build_registration_url, send_invitation_email
from ..forms import InvitationForm
from ..invite_chain import build_chain, descendant_users
from ..models import INVITATION_TTL, Invitation
from ..permissions import can_invite_users

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())


class CanInviteUsersMixin:
    """Require the ``can_invite_users`` capability on top of portal access."""

    def dispatch(self, request, *args, **kwargs):
        if not can_invite_users(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class InvitationScopeMixin:
    """Scope invitations to the ones the requesting user may act on.

    Ownership is enforced here rather than in the template so that detail,
    resend and revoke all inherit it: somebody else's invitation is simply
    not in your queryset, and every one of those views 404s on it.
    """

    def get_queryset(self):
        queryset = Invitation.objects.select_related("invited_by", "accepted_by")
        if self.request.user.is_superuser:
            return queryset
        return queryset.sent_by(self.request.user)


class InviteListView(CanInviteUsersMixin, InvitationScopeMixin, ListView):
    """The invitations you have sent, in every state."""

    template_name = "accounts/invite_list.html"
    context_object_name = "invitations"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invitations = context["invitations"]
        counts = {
            Invitation.Status.PENDING: 0,
            Invitation.Status.ACCEPTED: 0,
        }
        stale = 0
        for invitation in invitations:
            status = invitation.status
            if status in counts:
                counts[status] += 1
            else:
                stale += 1
        context["stats"] = [
            {"value": counts[Invitation.Status.PENDING], "label": "Waiting"},
            {"value": counts[Invitation.Status.ACCEPTED], "label": "Joined"},
            {"value": stale, "label": "Expired or revoked"},
        ]
        return context


class InviteCreateView(CanInviteUsersMixin, FormView):
    """Invite somebody new."""

    template_name = "accounts/invite_form.html"
    form_class = InvitationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["inviter"] = self.request.user
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        email = form.cleaned_data["email"]
        invitation = Invitation.objects.pending().filter(email__iexact=email).first()
        if invitation is None:
            invitation = form.save(commit=False)
            invitation.invited_by = self.request.user
            invitation.save()
        else:
            # Somebody already has a live link for this address — reuse it
            # rather than putting a second valid token into the world.
            messages.info(
                self.request,
                f"{email} already had an invitation waiting, so we sent that one again.",
            )
        _send_and_report(self.request, invitation)
        return redirect(invitation.get_absolute_url())


class InviteDetailView(CanInviteUsersMixin, InvitationScopeMixin, DetailView):
    """One invitation, with the shareable link and its lifecycle actions."""

    template_name = "accounts/invite_detail.html"
    context_object_name = "invitation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Only ever hand out a live link. A revoked or expired invitation
        # showing a copyable URL is an invitation to paste a dead link.
        if self.object.is_pending:
            context["registration_url"] = build_registration_url(self.object, self.request)
        return context


class InviteResendView(CanInviteUsersMixin, InvitationScopeMixin, View):
    """Re-send an invitation, extending its life.

    The token is deliberately unchanged: somebody who already has the first
    email should not find their link silently broken by a resend.
    """

    def post(self, request, pk):
        invitation = get_object_or_404(self.get_queryset(), pk=pk)
        if invitation.status in {Invitation.Status.ACCEPTED, Invitation.Status.REVOKED}:
            messages.error(request, f"That invitation is {invitation.status.value} — nothing sent.")
            return redirect(invitation.get_absolute_url())

        invitation.expires_at = timezone.now() + INVITATION_TTL
        invitation.save(update_fields=["expires_at", "updated_at"])
        _send_and_report(request, invitation)
        return redirect(invitation.get_absolute_url())


class InviteRevokeView(CanInviteUsersMixin, InvitationScopeMixin, View):
    """Kill an outstanding invitation's link."""

    def post(self, request, pk):
        invitation = get_object_or_404(self.get_queryset(), pk=pk)
        if invitation.accepted_at is not None:
            messages.error(
                request,
                "That invitation has already been accepted, so there is no link left to revoke.",
            )
            return redirect(invitation.get_absolute_url())

        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
        messages.success(request, f"Revoked the invitation for {invitation.email}.")
        return redirect("invite-list")


class InviteTreeView(TemplateView):
    """Who invited whom, across the whole site. Superuser only via ``access=``."""

    template_name = "accounts/invite_tree.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roots"] = build_chain()
        return context


class InviteSubtreePruneView(View):
    """Deactivate an account together with everyone it brought in.

    Deactivation, never deletion: the point of the chain is that a spammer's
    log entries, reports and machines stay readable after the accounts stop
    working. Reversal is a per-user ``is_active`` flip in the admin.
    """

    template_name = "accounts/invite_prune_confirm.html"

    def get_target(self):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def _refusal(self, request, target):
        """Return a refusal message, or ``None`` if pruning is allowed."""
        if target == request.user:
            return "You can't prune your own account."
        if target.is_superuser:
            return "Superusers can't be pruned. Remove the superuser flag first."
        return None

    def get(self, request, pk):
        del pk  # supplied via self.kwargs
        target = self.get_target()
        refusal = self._refusal(request, target)
        if refusal:
            messages.error(request, refusal)
            return redirect("invite-tree")

        return render(
            request,
            self.template_name,
            {"target": target, "descendants": descendant_users(target)},
        )

    @transaction.atomic
    def post(self, request, pk):
        del pk  # supplied via self.kwargs
        target = self.get_target()
        refusal = self._refusal(request, target)
        if refusal:
            messages.error(request, refusal)
            return redirect("invite-tree")

        affected = [target, *descendant_users(target)]
        affected_ids = [user.pk for user in affected]
        User.objects.filter(pk__in=affected_ids).update(is_active=False)
        Invitation.objects.pending().filter(invited_by_id__in=affected_ids).update(
            revoked_at=timezone.now()
        )

        messages.success(
            request,
            f"Deactivated {len(affected)} account(s) and revoked their outstanding invitations. "
            f"Their history is untouched.",
        )
        return redirect("invite-tree")


def _send_and_report(request, invitation: Invitation) -> None:
    """Send the invitation email and tell the inviter what happened.

    A failed send is reported, not raised: the invitation exists either way
    and the detail page we're about to redirect to carries the link.
    """
    if send_invitation_email(invitation, request):
        invitation.last_sent_at = timezone.now()
        invitation.save(update_fields=["last_sent_at", "updated_at"])
        messages.success(request, f"Invitation emailed to {invitation.email}.")
    else:
        messages.warning(
            request,
            f"We couldn't email {invitation.email}. The invitation is ready — "
            f"copy the link below and send it to them yourself.",
        )
