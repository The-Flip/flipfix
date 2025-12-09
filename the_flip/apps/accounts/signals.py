from django.contrib import messages
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver


@receiver(user_logged_out)
def show_logout_message(sender, request, **kwargs):
    messages.success(request, "You have logged out.")
