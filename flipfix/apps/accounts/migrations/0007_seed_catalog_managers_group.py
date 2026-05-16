"""Data migration to create the empty Catalog Managers group with can_manage_catalog."""

from django.db import migrations


def seed_catalog_managers_group(apps, schema_editor):
    """Create Catalog Managers group with the can_manage_catalog permission.

    The Permission row is created explicitly: the AlterModelOptions in
    0006 records the metadata change, but the actual Permission row is
    created later by the post_migrate signal, which runs after all
    migrations finish.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct, _ = ContentType.objects.get_or_create(app_label="accounts", model="maintainer")
    perm, _ = Permission.objects.get_or_create(
        codename="can_manage_catalog",
        content_type=ct,
        defaults={"name": "Can manage catalog (create machines, print QR codes)"},
    )
    group, _ = Group.objects.get_or_create(name="Catalog Managers")
    group.permissions.add(perm)
    # Intentionally do NOT seed any users; group starts empty.
    # Intentionally do NOT attach can_access_maintainer_portal — portal access
    # comes from membership in the Maintainers group.


def unseed_catalog_managers_group(apps, schema_editor):
    """Remove the Catalog Managers group.

    Matches the 0005 pattern: only the group is removed. The Permission
    row is intentionally left in place — deleting it would cascade
    through ``auth_group_permissions`` and ``auth_user_user_permissions``
    and silently revoke any out-of-band grants. Reversing 0006
    (AlterModelOptions) handles the metadata side.
    """
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Catalog Managers").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_alter_maintainer_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(seed_catalog_managers_group, unseed_catalog_managers_group),
    ]
