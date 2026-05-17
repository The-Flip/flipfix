import secrets
from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views import View
from django.views.generic import FormView, ListView, UpdateView

from .forms import (
    InvitationRegistrationForm,
    ProfileForm,
    TerminalCreateForm,
    TerminalUpdateForm,
)
from .models import Invitation, Maintainer
from .permissions import can_view_user_profiles

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())


def _make_maintainer(user: "UserType") -> Maintainer:
    """Create Maintainer profile and add user to Maintainers group."""
    from django.contrib.auth.models import Group

    maintainer, _ = Maintainer.objects.get_or_create(user=user)
    group = Group.objects.get(name="Maintainers")
    user.groups.add(group)
    return maintainer


def invitation_register(request, token):
    """Complete registration for an invited user."""
    invitation = get_object_or_404(Invitation, token=token)

    if invitation.used:
        messages.error(request, "This invitation has already been used.")
        return redirect("login")

    if request.method == "POST":
        form = InvitationRegistrationForm(request.POST)
        if form.is_valid():
            # Create the user
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
            )
            _make_maintainer(user)

            # Mark invitation as used
            invitation.used = True
            invitation.save()

            # Log the user in
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


class ProfileUpdateView(SuccessMessageMixin, UpdateView):
    """Allow users to update their profile information."""

    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("profile")
    success_message = "Profile updated successfully."

    def get_object(self, queryset=None):  # noqa: ARG002
        return self.request.user


class UserDirectoryView(ListView):
    """Public-to-maintainers directory of profile pages.

    Access: middleware gates this to logged-in maintainers (default
    ``access=None`` on the URL). ``dispatch()`` adds the extra
    ``can_view_user_profiles`` capability check on top — kept inline
    rather than via a mixin to mirror the per-view auth style in
    ``docs/Views.md``.
    """

    template_name = "accounts/user_directory.html"
    context_object_name = "maintainers"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_user_profiles(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Sort by the same character users read: first name if set,
        # otherwise username. Lower() is required because Postgres and
        # SQLite default collations are byte-order, so without it "alice"
        # would sort after "Zoe". .distinct() is defensive against the
        # user__groups M2M join inside in_user_directory() — today a user
        # can only be in the Maintainers group once, but the join could
        # silently produce duplicates if the predicate evolves.
        sort_key = Lower(Coalesce(NullIf("user__first_name", Value("")), "user__username"))
        # prefetch_related("media") loads every MaintainerMedia row per
        # maintainer (≤10 each) although the card only renders the first.
        # Fine at expected scale (dozens of maintainers); if the directory
        # grows past a few hundred, switch to a Subquery for the first-id
        # or a sliced Prefetch with to_attr.
        return (
            Maintainer.objects.in_user_directory()
            .select_related("user")
            .prefetch_related("media")
            .order_by(sort_key)
            .distinct()
        )


class TerminalListView(ListView):
    """List all shared terminal accounts."""

    template_name = "accounts/terminal_list.html"
    context_object_name = "terminals"

    def get_queryset(self):
        return Maintainer.objects.filter(is_shared_account=True).select_related("user")


class TerminalLoginView(View):
    """Log in as a shared terminal account."""

    def post(self, request, pk):
        terminal = get_object_or_404(
            Maintainer, pk=pk, is_shared_account=True, user__is_active=True
        )
        login(request, terminal.user)
        messages.success(request, f"Logged in as {terminal.display_name}.")
        return redirect("home")


class TerminalCreateView(FormView):
    """Create a new shared terminal account."""

    template_name = "accounts/terminal_form.html"
    form_class = TerminalCreateForm
    success_url = reverse_lazy("terminal-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_create"] = True
        return context

    @transaction.atomic
    def form_valid(self, form):
        # Create user with random password
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            first_name=form.cleaned_data.get("first_name") or "",
            last_name=form.cleaned_data.get("last_name") or "",
            password=secrets.token_urlsafe(32),
        )
        maintainer = _make_maintainer(user)
        maintainer.is_shared_account = True
        maintainer.save()

        messages.success(
            self.request,
            format_html(
                "Terminal '<a href=\"{}\">{}</a>' created.",
                reverse("terminal-edit", kwargs={"pk": maintainer.pk}),
                maintainer.display_name,
            ),
        )
        return super().form_valid(form)


class TerminalUpdateView(FormView):
    """Edit a shared terminal account."""

    template_name = "accounts/terminal_form.html"
    form_class = TerminalUpdateForm
    success_url = reverse_lazy("terminal-list")

    def get_terminal(self):
        return get_object_or_404(Maintainer, pk=self.kwargs["pk"], is_shared_account=True)

    def get_initial(self):
        terminal = self.get_terminal()
        return {
            "first_name": terminal.user.first_name,
            "last_name": terminal.user.last_name,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_create"] = False
        context["terminal"] = self.get_terminal()
        return context

    def form_valid(self, form):
        terminal = self.get_terminal()
        terminal.user.first_name = form.cleaned_data.get("first_name") or ""
        terminal.user.last_name = form.cleaned_data.get("last_name") or ""
        terminal.user.save()

        messages.success(
            self.request,
            format_html(
                "Terminal '<a href=\"{}\">{}</a>' updated.",
                reverse("terminal-edit", kwargs={"pk": terminal.pk}),
                terminal.display_name,
            ),
        )
        return super().form_valid(form)


class TerminalDeactivateView(View):
    """Deactivate a shared terminal account."""

    def post(self, request, pk):
        terminal = get_object_or_404(Maintainer, pk=pk, is_shared_account=True)
        terminal.user.is_active = False
        terminal.user.save()
        messages.success(
            request,
            format_html(
                "Terminal '<a href=\"{}\">{}</a>' deactivated.",
                reverse("terminal-edit", kwargs={"pk": terminal.pk}),
                terminal.display_name,
            ),
        )
        return redirect("terminal-list")


class TerminalReactivateView(View):
    """Reactivate a shared terminal account."""

    def post(self, request, pk):
        terminal = get_object_or_404(Maintainer, pk=pk, is_shared_account=True)
        terminal.user.is_active = True
        terminal.user.save()
        messages.success(
            request,
            format_html(
                "Terminal '<a href=\"{}\">{}</a>' reactivated.",
                reverse("terminal-edit", kwargs={"pk": terminal.pk}),
                terminal.display_name,
            ),
        )
        return redirect("terminal-list")
