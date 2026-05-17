"""Grant can_view_user_profiles to the Maintainers group.

Mirrors the pattern in 0005/0007: the Permission row is created explicitly
because the AlterModelOptions step that introduced ``can_view_user_profiles``
only updates the metadata. The actual ``auth_permission`` row is created by
the ``post_migrate`` signal, which runs after this migration, so a naive
``Permission.objects.get(codename=...)`` here would raise ``DoesNotExist``.
"""

from django.db import migrations


def grant_view_user_profiles(apps, schema_editor):
    """Create permission and grant it to the Maintainers group."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct, _ = ContentType.objects.get_or_create(app_label="accounts", model="maintainer")
    perm, _ = Permission.objects.get_or_create(
        codename="can_view_user_profiles",
        content_type=ct,
        defaults={"name": "Can view the user directory and profile pages"},
    )
    group, _ = Group.objects.get_or_create(name="Maintainers")
    group.permissions.add(perm)


def revoke_view_user_profiles(apps, schema_editor):
    """Remove the permission from the Maintainers group.

    Leaves the Permission row in place — matches 0007's reverse, where
    deleting permissions could silently revoke out-of-band grants.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        perm = Permission.objects.get(
            codename="can_view_user_profiles",
            content_type__app_label="accounts",
            content_type__model="maintainer",
        )
    except Permission.DoesNotExist:
        return
    for group in Group.objects.filter(name="Maintainers"):
        group.permissions.remove(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_alter_maintainer_options_maintainer_bio_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(grant_view_user_profiles, revoke_view_user_profiles),
    ]
