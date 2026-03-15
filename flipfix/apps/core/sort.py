"""Sorting utilities for human-friendly name ordering.

Provides a database-level annotation that strips leading articles
("The", "A", "An") so names sort by their significant word.
"The Addams Family" sorts under A, not T.

Usage::

    from flipfix.apps.core.sort import article_sort_key

    # Annotate and order by the sort key
    qs = (
        MachineModel.objects
        .annotate(sort_name=article_sort_key("name"))
        .order_by("sort_name")
    )

    # For related fields, pass the full lookup path
    qs = (
        MachineInstance.objects
        .annotate(sort_name=article_sort_key("model__name"))
        .order_by("sort_name")
    )
"""

from __future__ import annotations

from django.db.models import Case, CharField, When
from django.db.models.functions import Length, Lower, Substr


def article_sort_key(field: str) -> Case:
    """Return a Case expression that strips leading articles for sorting.

    Strips "The ", "A ", and "An " (case-insensitive) from the start of
    the field value, returning the remainder in lowercase. Non-matching
    values pass through as lowercase.

    Args:
        field: The field name or lookup path (e.g., "name", "model__name").

    Returns:
        A Case expression suitable for ``.annotate()`` or ``.order_by()``.
    """
    # Each article needs a When clause that checks for the prefix
    # and returns the substring after it.
    articles = [
        ("the ", 5),
        ("a ", 3),
        ("an ", 4),
    ]

    whens = []
    for article, skip in articles:
        whens.append(
            When(
                **{f"{field}__istartswith": article},
                then=Lower(Substr(field, skip, Length(field))),
            )
        )

    return Case(
        *whens,
        default=Lower(field),
        output_field=CharField(),
    )
