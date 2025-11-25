from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from .forms import InvitationRegistrationForm, ProfileForm
from .models import Invitation, Maintainer

User = get_user_model()


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
                is_staff=True,  # Maintainers need staff access
            )
            # Maintainer is auto-created via signal for staff users
            # but let's ensure it exists
            Maintainer.objects.get_or_create(user=user)

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

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)
