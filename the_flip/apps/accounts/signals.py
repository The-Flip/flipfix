from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Maintainer


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_maintainer_for_staff(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.is_staff:
        Maintainer.objects.get_or_create(user=instance)
