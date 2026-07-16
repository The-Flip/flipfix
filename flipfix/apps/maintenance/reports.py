"""Daily maintenance report: health classification, zone grouping, rendering.

Shared by the ``daily_maintenance_report`` management command, the Discord
posting task, and the maintainer web landing page. All database access lives in
:func:`build_report`; everything the renderers touch is a plain dataclass, so the
markdown digest and the HTML page stay in lockstep.

The emoji is the *player's* perspective (worst-wins over operational status and
open problem-report priorities). Task-priority reports are routine chores that
don't affect playability, so they never change the emoji. See
``docs/plans/DailyMaintenanceReport.md``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.maintenance.models import LogEntry, ProblemReport

# --------------------------------------------------------------------------
# Health states → emoji / labels
# --------------------------------------------------------------------------
# Order is best → worst; drives the legend and the worst-wins classification.
HEALTH_ORDER = ["good", "minor", "untriaged", "major", "fixing", "down", "unknown"]

EMOJI = {
    "good": "😀",
    "minor": "🙂",
    "untriaged": "🤔",
    "major": "😟",
    "fixing": "🔧",
    "down": "😭",
    "unknown": "😐",
}

LABELS = {
    "good": "good",
    "minor": "minor issue",
    "untriaged": "untriaged",
    "major": "major issue",
    "fixing": "being fixed",
    "down": "down",
    "unknown": "unknown",
}

# States that land a machine in the written "needs attention" list.
ATTENTION_STATES = ("down", "fixing", "major", "untriaged")

# Back-of-house "stalled" threshold: untouched this many days.
STALE_DAYS = 14

# Storage machines are parked, not health-tracked — they render as this box.
STORAGE_BOX = "📦"


def classify(status: str, priorities) -> str:
    """Collapse operational status + open-report priorities to one health state.

    The face is the player's perspective. Tasks (routine maintenance chores like
    "clean the playfield") don't affect playability, so they never worsen the
    emoji — ``priorities`` containing only Task reads the same as no reports.
    ``status`` already reflects the Unplayable→Broken invariant (enforced at
    write time by ``status_rules``), so it can be trusted directly.
    """
    s = MachineInstance.OperationalStatus
    if status == s.BROKEN or "unplayable" in priorities:
        return "down"
    if status == s.FIXING:
        return "fixing"
    if "major" in priorities:
        return "major"
    if "untriaged" in priorities:
        return "untriaged"
    if "minor" in priorities:
        return "minor"
    if status == s.UNKNOWN:
        return "unknown"
    return "good"


@dataclass(frozen=True)
class MachineHealth:
    """One machine's computed health plus the data the renderers need for links.

    Populated by :func:`build_report`; ``health`` is the result of
    :func:`classify`. Most fields default so the pure classifier tests can build
    minimal instances.
    """

    health: str
    status: str = "good"
    open_priorities: tuple[str, ...] = ()
    # dates (aware datetimes; renderers humanize):
    marked_down_at: datetime | None = None
    report_dates: Mapping[str, datetime] = field(default_factory=dict)
    last_worked_at: datetime | None = None
    worst_report_at: datetime | None = None
    # identity + link targets (populated by the builder):
    machine_id: int = 0
    slug: str = ""
    name: str = ""
    year: int | None = None
    location_slug: str = ""
    location_id: int | None = None
    zone: str = ""
    driving_report_id: int | None = None  # → problem-report-detail
    last_log_id: int | None = None  # → log-detail


def state_date(m: MachineHealth) -> datetime | None:
    """The date that matters for this machine's state.

    down → when it was marked down; untriaged/major → when the report came in;
    being fixed → date of the last log entry. Anything else falls back to the
    most recent activity.
    """
    if m.health == "fixing":
        return m.last_worked_at
    if m.health == "down":
        return m.marked_down_at
    if m.health == "untriaged":
        return m.report_dates.get("untriaged")
    if m.health == "major":
        return m.report_dates.get("major")
    return m.last_worked_at or m.worst_report_at


def humanize_ago(dt: datetime | None, now: datetime) -> str:
    """Coarse relative time ("yesterday", "7w ago"); "Unknown" when ``dt`` is None."""
    if dt is None:
        return "Unknown"
    delta = now - dt
    days = delta.days
    if days <= 0:
        hours = delta.seconds // 3600
        return "today" if hours < 1 else f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days}d ago"
    if days < 60:
        return f"{days // 7}w ago"
    return f"{days // 30}mo ago"


def stale_since(m: MachineHealth) -> datetime | None:
    """When work effectively stalled: last log, else the report date, else None."""
    return m.last_worked_at or m.worst_report_at


# --------------------------------------------------------------------------
# Report structure (what the renderers consume)
# --------------------------------------------------------------------------
MAX_ATTENTION = 5  # machines listed per zone


@dataclass(frozen=True)
class ZoneRow:
    """One location's machines as an emoji row (ordered oldest → newest)."""

    location_slug: str
    location_name: str
    cells: list[MachineHealth]
    is_storage: bool  # render cells as parked boxes, not health faces


@dataclass(frozen=True)
class Zone:
    """A report section (Front of House / Back of House)."""

    key: str  # "front" | "back"
    title: str
    pulse: str  # precomputed headline
    rows: list[ZoneRow]
    attention: list[MachineHealth]  # capped, most-recently-touched first


@dataclass(frozen=True)
class Report:
    generated_at: datetime
    zones: list[Zone]

    @property
    def legend(self) -> list[tuple[str, str]]:
        return [(EMOJI[k], LABELS[k]) for k in HEALTH_ORDER]


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------
_FRONT = Location.Zone.FRONT
_WORKSHOP = Location.Zone.WORKSHOP
_STORAGE = Location.Zone.STORAGE
REPORT_ZONES = (_FRONT, _WORKSHOP, _STORAGE)


def _marked_down_dates(machine_ids: list[int]) -> dict[int, datetime]:
    """When each machine's *current* broken streak began, in one history query.

    Walks each machine's history newest→oldest and records the oldest consecutive
    ``broken`` record. Empty for machines with no (or scrubbed) history — callers
    fall back to the driving report's date.
    """
    if not machine_ids:
        return {}
    historical = MachineInstance.history.model
    broken = MachineInstance.OperationalStatus.BROKEN
    rows = (
        historical.objects.filter(id__in=machine_ids)
        .order_by("id", "-history_date")
        .values_list("id", "operational_status", "history_date")
    )
    result: dict[int, datetime] = {}
    done: set[int] = set()
    for mid, status, when in rows:
        if mid in done:
            continue
        if status == broken:
            result[mid] = when  # keep moving the streak-start earlier
        else:
            done.add(mid)  # first non-broken (going back) ends the streak
    return result


def _driving_report_id(health: str, by_priority: dict) -> int | None:
    """The pk of the open report that 'won' the classification, if any."""
    key = {"down": "unplayable", "major": "major", "untriaged": "untriaged"}.get(health)
    if key and key in by_priority:
        return by_priority[key][0]
    return None


def _attention(machines: list[MachineHealth]) -> list[MachineHealth]:
    """Real issues only, most-recently-touched first, capped — surface active work.

    Never-touched machines (no log) sort to the end.
    """
    issues = [m for m in machines if m.health in ATTENTION_STATES]
    issues.sort(
        key=lambda m: (
            m.last_worked_at is not None,
            m.last_worked_at.timestamp() if m.last_worked_at else 0.0,
        ),
        reverse=True,
    )
    return issues[:MAX_ATTENTION]


def _rows(locations: list[Location], by_location: dict[int, list[MachineHealth]]) -> list[ZoneRow]:
    rows = []
    for loc in sorted(locations, key=lambda loc_: (loc_.sort_order, loc_.name)):
        cells = sorted(by_location.get(loc.pk, []), key=lambda m: (m.year is None, m.year or 0))
        if not cells:
            continue
        rows.append(
            ZoneRow(
                location_slug=loc.slug,
                location_name=loc.name,
                cells=cells,
                is_storage=loc.zone == _STORAGE,
            )
        )
    return rows


def build_report(now: datetime | None = None) -> Report:
    """Assemble the daily report from the DB in ~4 queries (no per-machine N+1)."""
    if now is None:
        now = timezone.localtime()

    machines = list(
        MachineInstance.objects.select_related("model", "location").filter(
            location__zone__in=REPORT_ZONES
        )
    )

    reports_by_machine: dict[int, list[dict]] = defaultdict(list)
    for r in ProblemReport.objects.filter(status=ProblemReport.Status.OPEN).values(
        "machine_id", "id", "priority", "occurred_at"
    ):
        reports_by_machine[r["machine_id"]].append(r)

    last_log: dict[int, dict] = {}
    for row in LogEntry.objects.order_by("machine_id", "-occurred_at").values(
        "machine_id", "id", "occurred_at"
    ):
        last_log.setdefault(row["machine_id"], row)

    # First pass: classify so we know which machines need a history lookup.
    prelim: dict[int, tuple] = {}
    down_ids: list[int] = []
    for m in machines:
        reports = reports_by_machine.get(m.id, [])
        priorities = {r["priority"] for r in reports}
        health = classify(m.operational_status, priorities)
        prelim[m.id] = (reports, priorities, health)
        if health == "down":
            down_ids.append(m.id)

    marked_down = _marked_down_dates(down_ids)

    healths: dict[int, MachineHealth] = {}
    for m in machines:
        reports, priorities, health = prelim[m.id]
        by_priority: dict[str, tuple[int, datetime]] = {}
        for r in reports:
            pr = r["priority"]
            if pr not in by_priority or r["occurred_at"] < by_priority[pr][1]:
                by_priority[pr] = (r["id"], r["occurred_at"])
        report_dates = {pr: v[1] for pr, v in by_priority.items()}
        worst_report_at = max((r["occurred_at"] for r in reports), default=None)
        log = last_log.get(m.id)

        m_marked_down = None
        if health == "down":
            m_marked_down = (
                marked_down.get(m.id) or report_dates.get("unplayable") or worst_report_at
            )

        healths[m.id] = MachineHealth(
            health=health,
            status=m.operational_status,
            open_priorities=tuple(r["priority"] for r in reports),
            marked_down_at=m_marked_down,
            report_dates=report_dates,
            last_worked_at=log["occurred_at"] if log else None,
            worst_report_at=worst_report_at,
            machine_id=m.id,
            slug=m.slug,
            name=m.short_display_name,
            year=m.model.year,
            location_slug=m.location.slug,
            location_id=m.location_id,
            zone=m.location.zone,
            driving_report_id=_driving_report_id(health, by_priority),
            last_log_id=log["id"] if log else None,
        )

    # Group locations + machines into the two zones.
    locations = {m.location_id: m.location for m in machines}
    by_location: dict[int, list[MachineHealth]] = defaultdict(list)
    for m in machines:
        by_location[m.location_id].append(healths[m.id])

    front_locs = [loc for loc in locations.values() if loc.zone == _FRONT]
    back_locs = [loc for loc in locations.values() if loc.zone in (_WORKSHOP, _STORAGE)]

    front_machines = [healths[m.id] for m in machines if m.location.zone == _FRONT]
    back_machines = [healths[m.id] for m in machines if m.location.zone in (_WORKSHOP, _STORAGE)]
    workshop_machines = [m for m in back_machines if m.zone == _WORKSHOP]

    front = Zone(
        key="front",
        title="Front of House",
        pulse=_front_pulse(front_machines),
        rows=_rows(front_locs, by_location),
        attention=_attention(front_machines),
    )
    back = Zone(
        key="back",
        title="Back of House",
        pulse=_back_pulse(back_machines, workshop_machines, now),
        rows=_rows(back_locs, by_location),
        attention=_attention(workshop_machines),  # storage is parked, not queued
    )
    return Report(generated_at=now, zones=[front, back])


def _front_pulse(machines: list[MachineHealth]) -> str:
    total = len(machines)
    playing = sum(1 for m in machines if m.health in ("good", "minor"))
    down = sum(1 for m in machines if m.health == "down")
    fixing = sum(1 for m in machines if m.health == "fixing")
    return f"{playing}/{total} playing well · {down} down · {fixing} being fixed"


def _back_pulse(back: list[MachineHealth], workshop: list[MachineHealth], now: datetime) -> str:
    total = len(back)
    ready = sum(1 for m in back if m.health == "good")
    stalled = 0
    for m in workshop:
        since = stale_since(m)
        if m.health in ATTENTION_STATES and since is not None and (now - since).days >= STALE_DAYS:
            stalled += 1
    return f"{total} in the shop · {stalled} stalled (>2w) · {ready} ready to return"


# --------------------------------------------------------------------------
# Rendering (markdown digest for Discord/CLI; verbose text for --verbose/HTML)
# --------------------------------------------------------------------------
# Per-location emoji, purely cosmetic; unknown slugs get a neutral pin.
LOCATION_ICONS = {"coin-op": "🪙", "museum": "🏛️", "workshop": "🛠️", "storage": "📦"}
DEFAULT_LOCATION_ICON = "📍"


def location_icon(slug: str) -> str:
    return LOCATION_ICONS.get(slug, DEFAULT_LOCATION_ICON)


def _legend_line(report: Report) -> str:
    return "_" + " · ".join(f"{e} {label}" for e, label in report.legend) + "_"


def _label_width(report: Report) -> int:
    return max((len(r.location_slug) for z in report.zones for r in z.rows), default=1) + 1


def _row_cells(row: ZoneRow) -> str:
    if row.is_storage:
        return STORAGE_BOX * len(row.cells)
    return "".join(EMOJI[c.health] for c in row.cells)


def _attention_line(m: MachineHealth, now: datetime) -> str:
    icon = location_icon(m.location_slug)
    return f"{EMOJI[m.health]} {icon} **{m.name}** — {LABELS[m.health]} · {humanize_ago(state_date(m), now)}"


def render_markdown(report: Report, *, link_url: str | None = None) -> str:
    """The compact "emoji-digest" — Discord webhook `content` and CLI default."""
    now = report.generated_at
    width = _label_width(report)
    blocks: list[str] = []
    for zone in report.zones:
        lines = [f"**{zone.title}:** {zone.pulse}"]
        for row in zone.rows:
            lines.append(
                f"{location_icon(row.location_slug)} `{row.location_slug.upper():<{width}}` {_row_cells(row)}"
            )
        if zone.attention:
            lines.append("")  # blank line before the machine list
            lines += [_attention_line(m, now) for m in zone.attention]
        blocks.append("\n".join(lines))

    parts = [*blocks, _legend_line(report)]
    if link_url:
        parts.append(f"🔗 Full board: {link_url}")
    return "\n\n".join(parts)


def render_verbose_text(report: Report) -> str:
    """Debug view: under each zone row, one line per machine with the inputs that
    drove its emoji. Mirrors what the HTML landing page shows."""
    now = report.generated_at
    width = _label_width(report)
    blocks: list[str] = []
    for zone in report.zones:
        lines = [f"{zone.title}: {zone.pulse}"]
        for row in zone.rows:
            lines.append(
                f"{location_icon(row.location_slug)} {row.location_slug.upper():<{width}} {_row_cells(row)}"
            )
            for c in row.cells:
                year = c.year if c.year is not None else "?"
                reports = ",".join(sorted(c.open_priorities)) or "none"
                lines.append(
                    f"    {EMOJI[c.health]} {c.name} ({year}) — status={c.status} · "
                    f"reports=[{reports}] → {c.health} · {humanize_ago(state_date(c), now)}"
                )
        blocks.append("\n".join(lines))
    return "\n\n".join([*blocks, _legend_line(report)])
