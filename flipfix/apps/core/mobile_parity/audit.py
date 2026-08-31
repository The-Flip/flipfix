"""Render every auditable page and diff its mobile view against its desktop view.

This module owns no database setup. Callers supply that: the management command
creates a throwaway test database, the regression test relies on ``TestCase``
rolling its transaction back. One code path, two entry points.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from constance.test import override_config
from django.test import Client

from flipfix.apps.core.mobile_parity import affordances, visibility
from flipfix.apps.core.mobile_parity.config import DESKTOP_WIDTH, MOBILE_WIDTH
from flipfix.apps.core.mobile_parity.css_rules import DisplayIndex, load_display_index
from flipfix.apps.core.mobile_parity.dom import parse_document
from flipfix.apps.core.mobile_parity.routes import (
    ANONYMOUS,
    MAINTAINER,
    SUPERUSER,
    AuditRoute,
    ParityFixtures,
    Persona,
    build_fixtures,
    enumerate_routes,
)

#: Personas are visited in a fixed order so reports diff cleanly.
PERSONA_ORDER: tuple[Persona, ...] = (MAINTAINER, SUPERUSER, ANONYMOUS)


@dataclass(frozen=True, order=True)
class Gap:
    """One affordance a page offers on desktop but not on mobile."""

    route: str
    persona: str
    key: str
    kind: str = field(compare=False)
    element: str = field(compare=False)
    label: str = field(compare=False)
    hidden_by: str = field(compare=False)
    revealed_at: int | None = field(compare=False)

    @property
    def identity(self) -> tuple[str, str, str]:
        """What the baseline matches on — deliberately not the descriptive bits."""
        return (self.route, self.persona, self.key)

    @property
    def is_action(self) -> bool:
        return self.kind == "action"


@dataclass(frozen=True)
class AuditResult:
    """Everything one full pass found."""

    gaps: tuple[Gap, ...]
    audited: tuple[tuple[str, str], ...]
    skipped: tuple[tuple[str, str], ...]
    mobile_width: int
    desktop_width: int
    index: DisplayIndex

    @property
    def actions(self) -> tuple[Gap, ...]:
        return tuple(gap for gap in self.gaps if gap.is_action)

    @property
    def content(self) -> tuple[Gap, ...]:
        return tuple(gap for gap in self.gaps if not gap.is_action)


def _client_for(persona: Persona, fixtures: ParityFixtures) -> Client:
    # A page that raises should be reported as a skipped 500, not abort the whole
    # audit: one broken view must not hide the parity picture for every other page.
    client = Client(raise_request_exception=False)
    if persona is MAINTAINER:
        client.force_login(fixtures.maintainer)
    elif persona is SUPERUSER:
        client.force_login(fixtures.superuser)
    return client


def _skip_reason(response) -> str | None:
    """Why this response is not an auditable page, or ``None`` if it is one.

    Doing this dynamically rather than from a list means POST-only endpoints,
    redirects, permission denials and non-HTML responses all drop out on their
    own, and stay dropped as the site changes.
    """
    if response.status_code != 200:
        return f"non-200 response ({response.status_code})"
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return f"non-html response ({content_type.split(';')[0] or 'unknown'})"
    if b"<body" not in response.content:
        return "html fragment, not a full page"
    return None


def _gaps_for_page(
    html: str,
    route: AuditRoute,
    persona: Persona,
    index: DisplayIndex,
    mobile_width: int,
    desktop_width: int,
) -> list[Gap]:
    root = parse_document(html)
    items = affordances.extract(root)

    mobile_keys = {
        affordance.key
        for element, affordance in items
        if visibility.is_visible(element, index, mobile_width)
    }
    desktop_only: dict[str, Gap] = {}

    for element, affordance in items:
        if affordance.key in mobile_keys or affordance.key in desktop_only:
            continue
        if not visibility.is_visible(element, index, desktop_width):
            continue
        concealment = visibility.concealment(element, index, mobile_width)
        desktop_only[affordance.key] = Gap(
            route=route.name,
            persona=persona.name,
            key=affordance.key,
            kind=affordance.kind,
            element=affordance.tag,
            label=affordance.label,
            hidden_by=concealment.selector if concealment else "",
            revealed_at=index.revealed_at(concealment.class_name) if concealment else None,
        )

    return sorted(desktop_only.values())


def run_audit(
    *,
    route_names: Iterable[str] | None = None,
    persona_names: Iterable[str] | None = None,
    mobile_width: int = MOBILE_WIDTH,
    desktop_width: int = DESKTOP_WIDTH,
) -> AuditResult:
    """Render every auditable page as every relevant persona and diff the two views.

    Requires a usable database; the caller owns creating and tearing that down.
    """
    wanted_routes = set(route_names) if route_names is not None else None
    wanted_personas = set(persona_names) if persona_names is not None else None

    index = load_display_index()
    fixtures = build_fixtures()
    routes, skipped = enumerate_routes(fixtures)
    if wanted_routes is not None:
        routes = [route for route in routes if route.name in wanted_routes]

    gaps: list[Gap] = []
    audited: list[tuple[str, str]] = []
    dynamic_skips: list[tuple[str, str]] = []

    for persona in PERSONA_ORDER:
        if wanted_personas is not None and persona.name not in wanted_personas:
            continue
        relevant = [route for route in routes if persona in route.personas]
        if not relevant:
            continue

        def visit(pending: Sequence[AuditRoute] = (), who: Persona = persona) -> None:
            client = _client_for(who, fixtures)
            for route in pending:
                response = client.get(route.url)
                reason = _skip_reason(response)
                if reason is not None:
                    dynamic_skips.append((f"{route.name} [{who.name}]", reason))
                    continue
                audited.append((route.name, who.name))
                gaps.extend(
                    _gaps_for_page(
                        response.content.decode(response.charset or "utf-8"),
                        route,
                        who,
                        index,
                        mobile_width,
                        desktop_width,
                    )
                )

        if persona.is_anonymous:
            # Guests only see anything at all while public access is switched on,
            # and entering the override once keeps its DB reads out of the loop.
            with override_config(PUBLIC_ACCESS_ENABLED=True):
                visit(relevant)
        else:
            visit(relevant)

    return AuditResult(
        gaps=tuple(sorted(gaps)),
        audited=tuple(sorted(audited)),
        skipped=tuple(sorted([*skipped, *dynamic_skips])),
        mobile_width=mobile_width,
        desktop_width=desktop_width,
        index=index,
    )
