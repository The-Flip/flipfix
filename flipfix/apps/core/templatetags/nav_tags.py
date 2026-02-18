"""Navigation component tags: desktop_nav, mobile_priority_bar, mobile_hamburger, user_dropdown.

Defines the main nav items once as data and provides four inclusion tags
that render each navigation variant with pre-computed active states.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django import template

from flipfix.apps.core.mixins import can_access_maintainer_portal
from flipfix.apps.core.routing import get_public_url_names

register = template.Library()

# ---- Nav item data ----------------------------------------------------------


@dataclass(frozen=True)
class _NavItem:
    """A navigation item with active-state detection rules.

    Each item uses exactly one matching strategy:
    - ``active_exact``: match when url_name is in the tuple (e.g. Machines)
    - ``active_contains``: match when the substring appears in url_name (e.g. Problems)
    """

    label: str
    url_name: str
    icon: str
    active_contains: str = ""
    active_exact: tuple[str, ...] = field(default_factory=tuple)
    in_mobile_bar: bool = True
    mobile_extra_class: str = ""


@dataclass(frozen=True)
class _AdminNavItem:
    """An admin navigation item. Uses exact url_name matching for active state."""

    label: str
    url_name: str
    icon: str
    track_active: bool = True


ADMIN_NAV_ITEMS: tuple[_AdminNavItem, ...] = (
    _AdminNavItem(label="Wall Display", url_name="wall-display-setup", icon="tv"),
    _AdminNavItem(label="Terminals", url_name="terminal-list", icon="display"),
    _AdminNavItem(
        label="Locations",
        url_name="admin:catalog_location_changelist",
        icon="location-dot",
        track_active=False,
    ),
    _AdminNavItem(
        label="Users",
        url_name="admin:accounts_invitation_add",
        icon="user-plus",
        track_active=False,
    ),
    _AdminNavItem(label="QR Codes", url_name="machine-qr-bulk", icon="qrcode"),
    _AdminNavItem(label="Site Settings", url_name="site-settings", icon="gear"),
    _AdminNavItem(
        label="Django Admin",
        url_name="admin:index",
        icon="toolbox",
        track_active=False,
    ),
)


MAIN_NAV_ITEMS: tuple[_NavItem, ...] = (
    _NavItem(
        label="Machines",
        url_name="maintainer-machine-list",
        icon="list",
        active_exact=("maintainer-machine-list", "maintainer-machine-detail"),
    ),
    _NavItem(
        label="Problems",
        url_name="problem-report-list",
        icon="triangle-exclamation",
        active_contains="problem",
    ),
    _NavItem(
        label="Logs",
        url_name="log-list",
        icon="screwdriver-wrench",
        active_contains="log-",  # trailing hyphen avoids matching "login"/"logout"
        mobile_extra_class="nav-priority__item--logs",
    ),
    _NavItem(
        label="Parts",
        url_name="part-request-list",
        icon="box-open",
        active_contains="part",
        mobile_extra_class="nav-priority__item--parts",
    ),
    _NavItem(
        label="Docs",
        url_name="wiki-home",
        icon="book",
        active_contains="wiki",
        in_mobile_bar=False,
    ),
)

# Routes that activate the hamburger button itself (pages only reachable
# via the hamburger, not already shown in the mobile priority bar).
_HAMBURGER_ACTIVE_ROUTES: frozenset[str] = frozenset(
    {item.url_name for item in ADMIN_NAV_ITEMS if item.track_active} | {"profile"},
)

# ---- Helpers ----------------------------------------------------------------


def _is_active(item: _NavItem, url_name: str) -> bool:
    """Check whether a nav item matches the current URL name."""
    if item.active_exact:
        return url_name in item.active_exact
    return item.active_contains != "" and item.active_contains in url_name


def _resolve_nav_items(url_name: str, *, public_only: bool = False) -> list[dict[str, str | bool]]:
    """Build nav item context dicts with active state resolved.

    When ``public_only`` is True, only items whose ``url_name`` is in the
    public URL name registry are included.  Used for guest navigation.
    """
    public_names = get_public_url_names() if public_only else None
    return [
        {
            "label": item.label,
            "url_name": item.url_name,
            "icon": item.icon,
            "is_active": _is_active(item, url_name),
            "in_mobile_bar": item.in_mobile_bar,
            "mobile_extra_class": item.mobile_extra_class,
        }
        for item in MAIN_NAV_ITEMS
        if public_names is None or item.url_name in public_names
    ]


def _resolve_admin_items(url_name: str) -> list[dict[str, str | bool]]:
    """Build admin item context dicts with active state resolved.

    Note: active-state comparison uses exact match on url_name, but
    resolver_match.url_name strips namespace prefixes (e.g. "admin:").
    Items with namespaced url_names must set track_active=False.
    """
    return [
        {
            "label": item.label,
            "url_name": item.url_name,
            "icon": item.icon,
            "is_active": item.track_active and url_name == item.url_name,
        }
        for item in ADMIN_NAV_ITEMS
    ]


def _get_url_name(context: dict) -> str:
    """Safely extract url_name from the request's resolver_match."""
    request = context.get("request")
    if request and request.resolver_match:
        return request.resolver_match.url_name or ""
    return ""


# ---- Tags -------------------------------------------------------------------


@register.inclusion_tag("components/nav/desktop.html", takes_context=True)
def desktop_nav(context: dict) -> dict:
    """Render the desktop navigation bar (visible at md+ breakpoints).

    Usage::

        {% load nav_tags %}
        {% desktop_nav %}
    """
    user = context["user"]
    url_name = _get_url_name(context)
    admin_items = _resolve_admin_items(url_name)
    return {
        "nav_items": _resolve_nav_items(
            url_name, public_only=not can_access_maintainer_portal(user)
        ),
        "admin_items": admin_items,
        "admin_active": any(item["is_active"] for item in admin_items),
        "user": user,
        "perms": context.get("perms"),
    }


@register.inclusion_tag("components/nav/mobile_priority_bar.html", takes_context=True)
def mobile_priority_bar(context: dict) -> dict:
    """Render the mobile priority+ navigation bar with icons.

    Only shows items where ``in_mobile_bar`` is True.

    Usage::

        {% load nav_tags %}
        {% mobile_priority_bar %}
    """
    user = context["user"]
    return {
        "nav_items": _resolve_nav_items(
            _get_url_name(context), public_only=not can_access_maintainer_portal(user)
        ),
        "user": user,
        "perms": context.get("perms"),
    }


@register.inclusion_tag("components/nav/mobile_hamburger.html", takes_context=True)
def mobile_hamburger(context: dict) -> dict:
    """Render the mobile hamburger dropdown with all nav items, admin links, and account.

    Usage::

        {% load nav_tags %}
        {% mobile_hamburger %}
    """
    user = context["user"]
    url_name = _get_url_name(context)
    nav_items = _resolve_nav_items(url_name, public_only=not can_access_maintainer_portal(user))

    # The hamburger button lights up when the current page is:
    # - A non-bar nav item that's active (e.g. Docs/wiki)
    # - An admin or account route only accessible via the hamburger
    hamburger_active = (
        any(item["is_active"] for item in nav_items if not item["in_mobile_bar"])
        or url_name in _HAMBURGER_ACTIVE_ROUTES
    )

    return {
        "nav_items": nav_items,
        "admin_items": _resolve_admin_items(url_name),
        "user": user,
        "perms": context.get("perms"),
        "hamburger_active": hamburger_active,
        "hamburger_active_for_logs": "log-" in url_name,
        "hamburger_active_for_parts": "part" in url_name,
        "profile_active": url_name == "profile",
    }


@register.inclusion_tag("components/nav/user_dropdown.html", takes_context=True)
def user_dropdown(context: dict) -> dict:
    """Render the desktop user avatar dropdown with account and logout.

    Usage::

        {% load nav_tags %}
        {% user_dropdown %}
    """
    return {
        "user": context["user"],
        "perms": context.get("perms"),
    }
