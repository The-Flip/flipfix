"""User lifecycle helpers for the accounts domain.

Provisioning a maintainer touches two things — the ``Maintainer`` profile
and the ``Maintainers`` group — and both the registration flow and shared
terminal creation need them done together. This lives beside
``permissions.py`` rather than inside a view module so no caller has to
import a sibling view package just to create a user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import Group

from .models import Maintainer

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType


def make_maintainer(user: UserType) -> Maintainer:
    """Create Maintainer profile and add user to Maintainers group."""
    maintainer, _ = Maintainer.objects.get_or_create(user=user)
    group = Group.objects.get(name="Maintainers")
    user.groups.add(group)
    return maintainer
