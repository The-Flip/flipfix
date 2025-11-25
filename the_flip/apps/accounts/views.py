from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from .forms import InvitationRegistrationForm, ProfileForm, SelfRegistrationForm
from .models import Invitation, Maintainer

User = get_user_model()


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
                    is_staff=True,
                )
                # Ensure Maintainer exists
                Maintainer.objects.get_or_create(user=user)

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
