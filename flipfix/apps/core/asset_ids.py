"""Utility for generating sequential asset IDs with a prefix.

Asset IDs follow the format ``<PREFIX><NNNN>`` (e.g., M0001, P0001).
The prefix identifies the asset type; the numeric suffix auto-increments
from the highest existing ID for that prefix.

Usage::

    from flipfix.apps.core.asset_ids import generate_asset_id

    class MachineInstance(models.Model):
        asset_id = models.CharField(max_length=10, unique=True, blank=True)

        def save(self, *args, **kwargs):
            if not self.asset_id:
                self.asset_id = generate_asset_id("M", MachineInstance)
            super().save(*args, **kwargs)
"""

from __future__ import annotations

from typing import Any

from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr


def generate_asset_id(
    prefix: str,
    model_class: Any,
    field_name: str = "asset_id",
    pad_width: int = 4,
) -> str:
    """Generate the next sequential asset ID for the given prefix.

    Queries *model_class* for the highest existing numeric suffix after
    *prefix*, increments it, and zero-pads to *pad_width* digits.

    Args:
        prefix: The asset type prefix (e.g., "M" for machines).
        model_class: The Django model class containing *field_name*.
        field_name: The CharField holding the asset ID (default: "asset_id").
        pad_width: Number of digits to zero-pad (default: 4).

    Returns:
        The next asset ID string, e.g. "M0001".
    """
    prefix_len = len(prefix)

    max_num = (
        model_class.objects.filter(**{f"{field_name}__startswith": prefix})
        .annotate(
            numeric_part=Cast(
                Substr(field_name, prefix_len + 1),
                output_field=IntegerField(),
            )
        )
        .aggregate(max_num=Max("numeric_part"))["max_num"]
    )

    next_num = (max_num or 0) + 1
    return f"{prefix}{next_num:0{pad_width}d}"
