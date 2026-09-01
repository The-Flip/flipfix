"""Grant can_invite_users to the Maintainers group.

Mirrors 0005/0007/0009: the Permission row is created explicitly because
the AlterModelOptions step in 0014 only updates the metadata. The actual
``auth_permission`` row is created by the ``post_migrate`` signal, which
runs after this migration, so a naive ``Permission.objects.get(...)`` here
would raise ``DoesNotExist``.

This is what makes "any maintainer can invite" true. Revoking it from one
person is a group/user edit in the admin, not a code change.
"""

from django.db import migrations


def grant_invite_users(apps, schema_editor):
    """Create permission and grant it to the Maintainers group."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct, _ = ContentType.objects.get_or_create(app_label="accounts", model="maintainer")
    perm, _ = Permission.objects.get_or_create(
        codename="can_invite_users",
        content_type=ct,
        defaults={"name": "Can invite new users"},
    )
    group, _ = Group.objects.get_or_create(name="Maintainers")
    group.permissions.add(perm)


def revoke_invite_users(apps, schema_editor):
    """Remove the permission from the Maintainers group.

    Leaves the Permission row in place — matches 0007/0009's reverse, where
    deleting permissions could silently revoke out-of-band grants.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        perm = Permission.objects.get(
            codename="can_invite_users",
            content_type__app_label="accounts",
            content_type__model="maintainer",
        )
    except Permission.DoesNotExist:
        return
    for group in Group.objects.filter(name="Maintainers"):
        group.permissions.remove(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_remove_invitation_used"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(grant_invite_users, revoke_invite_users),
    ]
