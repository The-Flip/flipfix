"""Accounts forms."""

from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password

from the_flip.apps.core.forms import StyledFormMixin

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())


class InvitationRegistrationForm(StyledFormMixin, forms.Form):
    """Form for invited users to complete their registration."""

    username = forms.CharField(
        max_length=150,
        help_text="150 characters or fewer. Letters, digits and @/./+/-/_.",
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        help_text="You can change this from the invitation email if needed.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password


class ProfileForm(StyledFormMixin, forms.ModelForm):
    """Form for users to update their profile information."""

    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already registered.")
        return email


class TerminalCreateForm(StyledFormMixin, forms.Form):
    """Form for creating shared terminal accounts."""

    username = forms.CharField(
        max_length=150,
        help_text="Login identifier for this terminal.",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-1p-ignore": "",
                "data-lpignore": "true",
            }
        ),
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-1p-ignore": "",
                "data-lpignore": "true",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-1p-ignore": "",
                "data-lpignore": "true",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username


class TerminalUpdateForm(StyledFormMixin, forms.Form):
    """Form for editing shared terminal accounts."""

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-1p-ignore": "",
                "data-lpignore": "true",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-1p-ignore": "",
                "data-lpignore": "true",
            }
        ),
    )


class SimplePasswordChangeForm(PasswordChangeForm):
    """Password change form without confirmation field.

    Removes the new_password2 field and adds show/hide toggle support.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove the confirmation field
        del self.fields["new_password2"]

    def clean_new_password1(self):
        """Validate the new password."""
        password = self.cleaned_data.get("new_password1")
        if password:
            validate_password(password, self.user)
        return password

    def clean(self):
        """Skip the password confirmation check."""
        # Don't call super().clean() since it checks new_password1 == new_password2
        return self.cleaned_data
