import secrets
from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views import View
from django.views.generic import FormView, ListView, UpdateView

from the_flip.apps.core.mixins import CanManageTerminalsMixin

from .forms import (
    InvitationRegistrationForm,
    ProfileForm,
    SelfRegistrationForm,
    TerminalCreateForm,
    TerminalUpdateForm,
)
from .models import Invitation, Maintainer

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


def is_claimable_user(user):
    """Check if a user account can be claimed (unclaimed and not admin)."""
    return user.email.endswith("@example.com") and not user.is_superuser


def check_username(request):
    """AJAX endpoint to check username availability and provide suggestions."""
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"available": False, "exists": False, "suggestions": []})

    # Check if this exact username exists
    try:
        user = User.objects.get(username__iexact=query)
        exists = True
        available = is_claimable_user(user)
    except User.DoesNotExist:
        exists = False
        available = True  # New username is available

    # Get suggestions (only claimable users, case-insensitive match)
    suggestions = list(
        User.objects.filter(
            username__icontains=query,
            email__endswith="@example.com",
            is_superuser=False,
        )
        .values_list("username", flat=True)
        .order_by("username")[:10]
    )

    return JsonResponse(
        {
            "available": available,
            "exists": exists,
            "suggestions": suggestions,
        }
    )


def self_register(request):
    """Self-registration view for beta period."""
    if request.method == "POST":
        form = SelfRegistrationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            email = form.cleaned_data.get("email") or ""
            first_name = form.cleaned_data.get("first_name") or ""
            last_name = form.cleaned_data.get("last_name") or ""

            if form.existing_user:
                # Claiming existing account
                user = form.existing_user
                user.set_password(password)
                user.email = email  # Clear @example.com or set new email
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                user.save()
            else:
                # Creating new account
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
                _make_maintainer(user)

            login(request, user)
            display_name = user.get_full_name() or user.username
            messages.success(request, f"Welcome to The Flip, {display_name}!")
            return redirect("home")
    else:
        form = SelfRegistrationForm()

    return render(request, "registration/self_register.html", {"form": form})


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


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Allow users to update their profile information."""

    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):  # noqa: ARG002
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)


class TerminalListView(CanManageTerminalsMixin, ListView):
    """List all shared terminal accounts."""

    template_name = "accounts/terminal_list.html"
    context_object_name = "terminals"

    def get_queryset(self):
        return Maintainer.objects.filter(is_shared_account=True).select_related("user")


class TerminalLoginView(CanManageTerminalsMixin, View):
    """Log in as a shared terminal account."""

    def post(self, request, pk):
        terminal = get_object_or_404(
            Maintainer, pk=pk, is_shared_account=True, user__is_active=True
        )
        login(request, terminal.user)
        messages.success(request, f"Logged in as {terminal.display_name}.")
        return redirect("home")


class TerminalCreateView(CanManageTerminalsMixin, FormView):
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


class TerminalUpdateView(CanManageTerminalsMixin, FormView):
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


class TerminalDeactivateView(CanManageTerminalsMixin, View):
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


class TerminalReactivateView(CanManageTerminalsMixin, View):
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
