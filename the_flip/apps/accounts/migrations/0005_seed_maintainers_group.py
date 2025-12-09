"""Data migration to create Maintainers group and seed existing users."""

from django.db import migrations


def seed_maintainers_group(apps, schema_editor):
    """Create Maintainers group with permission and add all existing maintainers."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Maintainer = apps.get_model("accounts", "Maintainer")

    # Get or create the content type for Maintainer model
    ct, _ = ContentType.objects.get_or_create(app_label="accounts", model="maintainer")

    # Get or create the permission
    perm, _ = Permission.objects.get_or_create(
        codename="can_access_maintainer_portal",
        content_type=ct,
        defaults={"name": "Can access the maintainer portal"},
    )

    # Create "Maintainers" group with the permission
    group, _ = Group.objects.get_or_create(name="Maintainers")
    group.permissions.add(perm)

    # Add all existing maintainers to the group
    for maintainer in Maintainer.objects.select_related("user"):
        maintainer.user.groups.add(group)


def reverse_seed(apps, schema_editor):
    """Remove the Maintainers group (users will lose group membership)."""
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Maintainers").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_add_maintainer_portal_permission"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(seed_maintainers_group, reverse_seed),
    ]
