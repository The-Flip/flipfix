"""The signed-in user's own account page, including profile media."""

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from flipfix.apps.core.mixins import MediaUploadMixin

from ..forms import MaintainerProfileForm, ProfileForm
from ..models import Maintainer, MaintainerMedia
from ..permissions import is_in_user_directory

MAX_PROFILE_MEDIA = 10


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
