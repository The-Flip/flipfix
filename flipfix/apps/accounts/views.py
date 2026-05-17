import secrets
from typing import TYPE_CHECKING, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, FormView, ListView, UpdateView

from flipfix.apps.core.mixins import MediaUploadMixin

from .forms import (
    InvitationRegistrationForm,
    MaintainerProfileForm,
    ProfileForm,
    TerminalCreateForm,
    TerminalUpdateForm,
)
from .models import Invitation, Maintainer, MaintainerMedia
from .permissions import can_view_user_profiles, is_in_user_directory

MAX_PROFILE_MEDIA = 10

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


class ProfileUpdateView(MediaUploadMixin, UpdateView):
    """Allow users to update their profile information and manage profile media.

    Two sibling ModelForms (``ProfileForm`` for User, ``MaintainerProfileForm``
    for Maintainer) render together and save atomically. Profile media
    (upload / delete / reorder) is managed inline via AJAX actions on this
    same view, dispatched through ``MediaUploadMixin``.

    ``SuccessMessageMixin`` is deliberately not used: it's coupled to the
    default ``form_valid()`` flow, which we bypass to drive two forms.
    """

    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        del queryset  # unused — UpdateView signature requires the parameter
        return self.request.user

    def _get_maintainer(self) -> Maintainer | None:
        """Return the request user's Maintainer profile, or ``None``.

        ``/profile`` is gated to ``authenticated`` (not ``maintainer``) —
        non-maintainer authenticated users can land here, so the bio +
        media UI must degrade gracefully.
        """
        return getattr(self.request.user, "maintainer", None)

    # -- MediaUploadMixin wiring --------------------------------------------

    def get_media_model(self):
        return MaintainerMedia

    def get_media_parent(self) -> Maintainer:
        # post() guards action-handlers behind is_in_user_directory, so
        # this is only reached for users with a Maintainer profile.
        maintainer = self._get_maintainer()
        if maintainer is None:
            raise RuntimeError("get_media_parent called without a Maintainer")
        return maintainer

    # -- Two-form rendering -------------------------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        maintainer = self._get_maintainer()
        if "maintainer_form" not in context and maintainer is not None:
            context["maintainer_form"] = MaintainerProfileForm(instance=maintainer)
        if maintainer is not None:
            context["profile_media"] = list(MaintainerMedia.objects.filter(maintainer=maintainer))
        return context

    # -- POST dispatch ------------------------------------------------------

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        # Set self.object so MediaUploadMixin's default self.object access
        # (inherited from DetailView convention) has something sane, even
        # though our handlers route through get_media_parent().
        self.object = self.get_object()
        action = request.POST.get("action")

        action_handlers = {
            "upload_media": self._handle_profile_upload,
            "delete_media": self.handle_delete_media,
            "reorder_media": self.handle_reorder_media,
        }
        if action in action_handlers:
            # Match the template-level visibility gate: only directory
            # members can mutate profile media. Excludes anonymous users,
            # users without a Maintainer, inactive users, and shared
            # terminal accounts — same single-source-of-truth predicate
            # used by the directory listing and the profile detail view.
            if not is_in_user_directory(request.user):
                return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
            return action_handlers[action](request)

        return self._save_profile_forms(request)

    # -- Action handlers ----------------------------------------------------

    def _handle_profile_upload(self, request: HttpRequest) -> JsonResponse:
        """Wrap ``handle_upload_media`` with the 10-item cap.

        TOCTOU: two simultaneous uploads from two tabs could both pass the
        count and create an 11th row. Acknowledged, not locked — the window
        is negligible for a single-user feature and select_for_update would
        be over-engineering.
        """
        existing = MaintainerMedia.objects.filter(maintainer=self.get_media_parent()).count()
        if existing >= MAX_PROFILE_MEDIA:
            return JsonResponse(
                {"success": False, "error": f"Maximum {MAX_PROFILE_MEDIA} items"},
                status=400,
            )
        return self.handle_upload_media(request)

    def _save_profile_forms(self, request: HttpRequest) -> HttpResponse:
        """Validate and save the profile form(s).

        Not a fall-through to ``super().post()`` because UpdateView only
        knows about ``form_class`` (ProfileForm) and would silently ignore
        the maintainer form. Non-maintainer users skip ``maintainer_form``
        entirely (see ``_get_maintainer``).
        """
        user = self.get_object()
        maintainer = self._get_maintainer()
        profile_form = ProfileForm(request.POST, instance=user)
        maintainer_form = (
            MaintainerProfileForm(request.POST, instance=maintainer) if maintainer else None
        )

        forms_valid = profile_form.is_valid() and (
            maintainer_form is None or maintainer_form.is_valid()
        )
        if forms_valid:
            if maintainer_form is not None:
                with transaction.atomic():
                    profile_form.save()
                    maintainer_form.save()
            else:
                profile_form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect(self.get_success_url())

        context = self.get_context_data(form=profile_form, maintainer_form=maintainer_form)
        return render(request, self.template_name, context)


class UserProfileDetailView(DetailView):
    """Profile detail page at ``/users/<username>/``.

    Same access pattern as ``UserDirectoryView``: middleware gates to
    logged-in maintainers, ``dispatch()`` layers ``can_view_user_profiles``
    on top. The queryset is ``Maintainer.objects.in_user_directory()`` —
    single source of truth — so any maintainer who would not appear in the
    directory listing also 404s here.
    """

    template_name = "accounts/user_profile.html"
    context_object_name = "maintainer"
    slug_field = "user__username"
    slug_url_kwarg = "username"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_user_profiles(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Maintainer.objects.in_user_directory().select_related("user").prefetch_related("media")
        )


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
        # Primary sort: most recently active first, so volunteers who actually
        # use the system surface to the top and lapsed accounts drift down.
        # Never-seen maintainers (NULL last_active_at) fall to the bottom and
        # use the alphabetical tiebreaker.
        #
        # Tiebreaker: the same character users read — first name if set,
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
            .order_by(F("last_active_at").desc(nulls_last=True), sort_key)
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
