"""Zone the existing museum locations so the daily report isn't empty on day one.

Matches on slug (not pk) and is reversible — reverse resets every location to the
`hidden` default. New/unmatched locations stay `hidden` until a maintainer assigns
a zone in the admin.
"""

from __future__ import annotations

from django.db import migrations

# slug -> Location.Zone value
ZONE_BY_SLUG = {
    "coin-op": "front",
    "museum": "front",
    "workshop": "workshop",
    "storage": "storage",
}


def apply_zones(apps, schema_editor):
    Location = apps.get_model("catalog", "Location")
    for slug, zone in ZONE_BY_SLUG.items():
        Location.objects.filter(slug=slug).update(zone=zone)


def reset_zones(apps, schema_editor):
    Location = apps.get_model("catalog", "Location")
    Location.objects.filter(slug__in=ZONE_BY_SLUG).update(zone="hidden")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0022_location_zone"),
    ]

    operations = [
        migrations.RunPython(apply_zones, reset_zones),
    ]
