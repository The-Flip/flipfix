"""Scan existing usernames for collisions with RESERVED_USERNAMES.

Forward-only protection in the registration forms only stops *new*
collisions. An existing user named, say, ``admin`` or ``me`` would
silently shadow a future ``/users/<reserved>/`` route once the
directory catch-all (``/users/<str:username>/``) lands. This migration
runs at deploy time and fails loudly if any existing username collides,
so the operator can rename the user before deploying.

If a collision is found, the deploy aborts and the operator must either
rename the offending user, or remove the name from ``RESERVED_USERNAMES``
and accept the routing implications.
"""

from django.conf import settings
from django.db import migrations

# Snapshot of RESERVED_USERNAMES at the time of this migration. Inlined
# (not imported) so that future changes to the constant in
# accounts/models.py do not retroactively alter what this migration
# checked at deploy time.
_RESERVED_USERNAMES_SNAPSHOT = frozenset(
    {
        "me",
        "search",
        "invite",
        "admin",
        "new",
        "edit",
        "delete",
        "settings",
    }
)


def check_reserved_usernames(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    collisions = list(
        User.objects.filter(username__in=_RESERVED_USERNAMES_SNAPSHOT).values_list(
            "username", flat=True
        )
    )
    if collisions:
        raise RuntimeError(
            "Found existing usernames that collide with RESERVED_USERNAMES: "
            f"{collisions}. Rename these users before deploying, or remove the "
            "names from RESERVED_USERNAMES in accounts/models.py."
        )


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op: the forward step only reads."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_grant_view_user_profiles_to_maintainers"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(check_reserved_usernames, noop_reverse),
    ]
