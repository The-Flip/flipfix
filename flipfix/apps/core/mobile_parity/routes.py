"""Decide which pages to audit, as whom, and with what fixture data.

Routes are enumerated automatically from the project's own ``path()`` registry
rather than from a hand-kept list. A curated list silently misses new pages,
which is exactly the regression this audit exists to catch; enumeration fails
the other way, turning a new page red until someone maps or excludes it.

Only routes registered through :mod:`flipfix.apps.core.routing` are considered,
which conveniently leaves Django's own admin out of scope without a single
exclusion entry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.urls import NoReverseMatch, get_resolver, reverse

from flipfix.apps.core.routing import get_registered_routes

if TYPE_CHECKING:  # pragma: no cover - typing only
    from flipfix.apps.accounts.models import Maintainer
    from flipfix.apps.catalog.models import MachineInstance, MachineModel, Owner
    from flipfix.apps.maintenance.models import LogEntry, ProblemReport
    from flipfix.apps.parts.models import PartRequest, PartRequestUpdate
    from flipfix.apps.wiki.models import WikiPage


class UnmappedRouteError(Exception):
    """A parameterised route has neither fixture kwargs nor an exclusion.

    Raised rather than skipped: a new page must be deliberately audited or
    deliberately left out, never quietly dropped.
    """


# --- Personas --------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    """A kind of visitor whose view of the site we audit."""

    name: str
    is_anonymous: bool


#: The default state most of the UI targets, and the only persona for which
#: ``can_access_maintainer_portal`` is true — so it is the only one that
#: exercises ``.avatar-dropdown--mobile-hidden`` and therefore the only one that
#: proves the hamburger supplies the account actions instead.
MAINTAINER = Persona(name="maintainer", is_anonymous=False)

#: Guest browsing with ``PUBLIC_ACCESS_ENABLED``. A materially different DOM:
#: the avatar dropdown loses its mobile-hidden class and every
#: ``{% if user.is_authenticated %}`` block disappears.
ANONYMOUS = Persona(name="anonymous", is_anonymous=True)

#: The only way to reach ``access="superuser"`` pages, and what pins down the
#: admin-menu parity that is currently accidental rather than enforced.
SUPERUSER = Persona(name="superuser", is_anonymous=False)

#: A plain authenticated non-maintainer is deliberately absent: its only unique
#: surface is the profile and password-change pages, both already covered by
#: MAINTAINER, and it is denied everywhere else.
PERSONAS_BY_ACCESS: Mapping[str | None, tuple[Persona, ...]] = {
    None: (MAINTAINER,),
    "authenticated": (MAINTAINER,),
    "public": (MAINTAINER, ANONYMOUS),
    "always_public": (MAINTAINER, ANONYMOUS),
    "superuser": (SUPERUSER,),
}


# --- Exclusions ------------------------------------------------------------

#: Route-name prefixes that never render an auditable page.
EXCLUDED_PREFIXES: Mapping[str, str] = {
    "api-": "json api endpoint",
    "oauth2-": "oauth2 / oidc protocol endpoint",
}

#: Route-name suffixes for HTML fragments rendered into an existing page.
EXCLUDED_SUFFIXES: Mapping[str, str] = {
    "-entries": "html partial (infinite scroll)",
    "-autocomplete": "html partial (autocomplete)",
    "-log-entries": "html partial",
    "-partial": "html partial",
}

#: Named routes that do return a full HTML page but should not be audited.
#: Everything else that is not auditable — POST-only endpoints, redirects,
#: non-HTML responses — is dropped dynamically by :mod:`audit`, which is
#: self-maintaining in a way a list like this is not.
EXCLUDED_ROUTES: Mapping[str, str] = {
    "wall-display-board": "fixed-size kiosk display, never viewed on a phone",
    "machine-qr": "renders a QR code sheet for printing, not a browsable page",
    "machine-qr-bulk": "renders a QR code sheet for printing, not a browsable page",
    "admin-debug-dashboard": "staff diagnostics, deliberately unstyled",
    "healthz": "plain-text health probe",
    "media": "serves uploaded files",
    "invitation-register": "requires a live single-use invitation token",
}


# --- Fixtures --------------------------------------------------------------


@dataclass
class ParityFixtures:
    """Objects the parameterised routes point at.

    Deliberately *rich*: optional relations are populated so that markup behind
    ``{% if machine.owner %}`` and friends actually renders. Anything left unset
    here is simply invisible to the audit, so this is a coverage surface.
    """

    machine: MachineInstance
    machine_model: MachineModel
    owner: Owner
    problem_report: ProblemReport
    log_entry: LogEntry
    part_request: PartRequest
    part_request_update: PartRequestUpdate
    wiki_page: WikiPage
    wiki_path: str
    task_slug: str
    terminal: Maintainer
    maintainer: User
    superuser: User


def build_fixtures() -> ParityFixtures:
    """Create the object graph the audit renders against."""
    from flipfix.apps.catalog.models import Owner
    from flipfix.apps.core.test_utils import (
        create_location,
        create_log_entry,
        create_machine,
        create_machine_model,
        create_maintainer_user,
        create_part_request,
        create_part_request_update,
        create_problem_report,
        create_shared_terminal,
        create_superuser,
    )
    from flipfix.apps.maintenance.models import MaintenanceTaskType
    from flipfix.apps.wiki.models import WikiPage, WikiPageTag

    maintainer = create_maintainer_user(username="parity-maintainer")
    superuser = create_superuser(username="parity-superuser")
    terminal = create_shared_terminal(username="parity-terminal")

    owner = Owner.objects.create(name="Parity Owner", slug="parity-owner")
    location = create_location(name="Parity Floor")
    machine_model = create_machine_model(name="Parity Model")
    machine = create_machine(
        model=machine_model,
        name="Parity Machine",
        slug="parity-machine",
        location=location,
        owner=owner,
        asset_id="M9001",
    )

    problem_report = create_problem_report(machine=machine, description="Parity problem")
    log_entry = create_log_entry(machine=machine, text="Parity log", created_by=maintainer)
    part_request = create_part_request(
        text="Parity part", machine=machine, requested_by=maintainer.maintainer
    )
    part_request_update = create_part_request_update(
        part_request=part_request, posted_by=maintainer.maintainer, text="Parity update"
    )

    task = MaintenanceTaskType.objects.create(
        name="Parity Task", slug="parity-task", is_active=True
    )

    wiki_page = WikiPage.objects.create(
        slug="parity-doc",
        title="Parity Doc",
        content="Parity body text",
        created_by=maintainer,
        updated_by=maintainer,
    )
    WikiPageTag.objects.create(page=wiki_page, tag="guides", slug=wiki_page.slug)

    return ParityFixtures(
        machine=machine,
        machine_model=machine_model,
        owner=owner,
        problem_report=problem_report,
        log_entry=log_entry,
        part_request=part_request,
        part_request_update=part_request_update,
        wiki_page=wiki_page,
        wiki_path=f"guides/{wiki_page.slug}",
        task_slug=task.slug,
        terminal=terminal,
        maintainer=maintainer,
        superuser=superuser,
    )


#: How to fill each parameterised route's URL kwargs. A parameterised route
#: missing from here — and not excluded — raises :class:`UnmappedRouteError`.
ROUTE_KWARGS: Mapping[str, Callable[[ParityFixtures], dict[str, object]]] = {
    "log-create-machine": lambda f: {"slug": f.machine.slug},
    "log-create-problem-report": lambda f: {"pk": f.problem_report.pk},
    "log-detail": lambda f: {"pk": f.log_entry.pk},
    "log-entry-edit": lambda f: {"pk": f.log_entry.pk},
    "machine-create-model-exists": lambda f: {"model_slug": f.machine_model.slug},
    "machine-details": lambda f: {"slug": f.machine.slug},
    "machine-edit": lambda f: {"slug": f.machine.slug},
    "machine-inline-update": lambda f: {"slug": f.machine.slug},
    "machine-mark-task-done": lambda f: {"slug": f.machine.slug, "task_slug": f.task_slug},
    "machine-model-edit": lambda f: {"slug": f.machine_model.slug},
    "maintainer-machine-detail": lambda f: {"slug": f.machine.slug},
    "owner-detail": lambda f: {"slug": f.owner.slug},
    "owner-edit": lambda f: {"slug": f.owner.slug},
    "part-request-create-machine": lambda f: {"slug": f.machine.slug},
    "part-request-detail": lambda f: {"pk": f.part_request.pk},
    "part-request-edit": lambda f: {"pk": f.part_request.pk},
    "part-request-status-update": lambda f: {"pk": f.part_request.pk},
    "part-request-update-create": lambda f: {"pk": f.part_request.pk},
    "part-request-update-detail": lambda f: {"pk": f.part_request_update.pk},
    "part-request-update-edit": lambda f: {"pk": f.part_request_update.pk},
    "part-request-updates": lambda f: {"pk": f.part_request.pk},
    "problem-report-create-machine": lambda f: {"slug": f.machine.slug},
    "problem-report-detail": lambda f: {"pk": f.problem_report.pk},
    "problem-report-edit": lambda f: {"pk": f.problem_report.pk},
    "public-machine-detail": lambda f: {"slug": f.machine.slug},
    "public-problem-report-create": lambda f: {"code": f.machine.asset_id},
    "terminal-deactivate": lambda f: {"pk": f.terminal.pk},
    "terminal-edit": lambda f: {"pk": f.terminal.pk},
    "terminal-login": lambda f: {"pk": f.terminal.pk},
    "terminal-reactivate": lambda f: {"pk": f.terminal.pk},
    "user-profile": lambda f: {"username": f.maintainer.username},
    "wiki-page-delete": lambda f: {"path": f.wiki_path},
    "wiki-page-detail": lambda f: {"path": f.wiki_path},
    "wiki-page-edit": lambda f: {"path": f.wiki_path},
    "wiki-template-prefill": lambda f: {
        "page_pk": f.wiki_page.pk,
        "template_name": "parity-template",
    },
}


@dataclass(frozen=True)
class AuditRoute:
    """One page to fetch, and the personas to fetch it as."""

    name: str
    url: str
    access: str | None
    personas: tuple[Persona, ...]


def static_exclusion(name: str) -> str | None:
    """Return why ``name`` is excluded up front, or ``None`` to audit it."""
    if name in EXCLUDED_ROUTES:
        return EXCLUDED_ROUTES[name]
    for suffix, reason in EXCLUDED_SUFFIXES.items():
        if name.endswith(suffix):
            return reason
    for prefix, reason in EXCLUDED_PREFIXES.items():
        if name.startswith(prefix):
            return reason
    return None


def enumerate_routes(fixtures: ParityFixtures) -> tuple[list[AuditRoute], list[tuple[str, str]]]:
    """Return the routes to audit, plus ``(name, reason)`` for those skipped.

    Raises:
        UnmappedRouteError: for a parameterised route with no fixture mapping.
    """
    # The registry fills as the URLconf is imported, and Django imports it
    # lazily. Touching the resolver first guarantees a complete picture rather
    # than however much happened to be loaded by the caller.
    resolver = get_resolver()
    _ = resolver.url_patterns
    reversible = set(resolver.reverse_dict.keys())

    audited: list[AuditRoute] = []
    skipped: list[tuple[str, str]] = []

    for name, access in sorted(get_registered_routes().items()):
        reason = static_exclusion(name)
        if reason is not None:
            skipped.append((name, reason))
            continue

        if name not in reversible:
            # The registry is process-global, so a test URLconf that uses our
            # path() leaves its dummy names behind. Those are not pages of this
            # site. Names that *are* in the URLconf but need arguments still
            # fall through to the UnmappedRouteError below.
            skipped.append((name, "not part of the active URLconf"))
            continue

        builder = ROUTE_KWARGS.get(name)
        kwargs = builder(fixtures) if builder else {}
        try:
            url = reverse(name, kwargs=kwargs)
        except NoReverseMatch as error:
            raise UnmappedRouteError(
                f"{name!r} takes URL parameters but has no ROUTE_KWARGS entry and no "
                f"exclusion. Add one to flipfix/apps/core/mobile_parity/routes.py so the "
                f"page is either audited or deliberately skipped. ({error})"
            ) from error

        audited.append(
            AuditRoute(
                name=name,
                url=url,
                access=access,
                personas=PERSONAS_BY_ACCESS[access],
            )
        )

    return audited, skipped
