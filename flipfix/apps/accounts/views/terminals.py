"""Shared workshop terminal accounts."""

import secrets
from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views import View
from django.views.generic import FormView, ListView

from ..forms import TerminalCreateForm, TerminalUpdateForm
from ..lifecycle import make_maintainer
from ..models import Maintainer

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())


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
        maintainer = make_maintainer(user)
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
