"""URL utility functions for building filter URLs."""

from django.http import QueryDict


def build_filter_url(path: str, current_params: QueryDict, **overrides: str | None) -> str:
    """Build a URL with query parameters, setting or clearing specified keys.

    Args:
        path: The request path (e.g. "/machines/").
        current_params: The current GET QueryDict.
        **overrides: Keys to set or clear. A value of None removes the key.

    Returns:
        URL string with updated query parameters.
    """
    params = current_params.copy()
    for key, value in overrides.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    # Reset pagination when changing filters
    params.pop("page", None)
    qs = params.urlencode()
    return f"{path}?{qs}" if qs else path
