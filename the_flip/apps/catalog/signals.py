"""Django signals for catalog models."""

from django.contrib import messages
from django.db.models.signals import post_save
from django.dispatch import receiver

from the_flip.apps.catalog.models import MachineModel


@receiver(post_save, sender=MachineModel)
def machine_model_saved_message(sender, instance, created, **kwargs):
    """Add success message when machine model is saved."""
    request = getattr(instance, "_request", None)
    if request:
        if created:
            messages.success(request, f"Model '{instance.name}' created.")
        else:
            messages.success(request, f"Model '{instance.name}' saved.")
