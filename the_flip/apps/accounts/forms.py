"""Accounts forms."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class InvitationRegistrationForm(forms.Form):
    """Form for invited users to complete their registration."""

    username = forms.CharField(
        max_length=150,
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
    )
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(help_text="You can change this from the invitation email if needed.")
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

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

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    """Form for users to update their profile information."""

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already registered.")
        return email


class SelfRegistrationForm(forms.Form):
    """Form for self-registration during beta period."""

    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.existing_user = kwargs.pop("existing_user", None)
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"]
        try:
            user = User.objects.get(username=username)
            # Check if claimable: has @example.com email and not admin
            if user.is_superuser:
                raise forms.ValidationError("This username is not available.")
            if not user.email.endswith("@example.com"):
                raise forms.ValidationError("This username is already taken.")
            # Store the existing user for later use
            self.existing_user = user
        except User.DoesNotExist:
            # New user - that's fine
            self.existing_user = None
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            # Check uniqueness, excluding the user being claimed
            qs = User.objects.filter(email=email)
            if self.existing_user:
                qs = qs.exclude(pk=self.existing_user.pk)
            if qs.exists():
                raise forms.ValidationError("This email is already registered.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password
