"""Accounts domain models."""
from django.conf import settings
from django.db import models

from the_flip.apps.core.models import TimeStampedModel


class Maintainer(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        full_name = self.user.get_full_name()
        return full_name or self.user.get_username()
