"""Reconstruct and cluster the historical Discord notification stream.

Dev-only analysis command (Phase 2 of the "coalesce spammy notifications" TODO).
It replays every record creation that *would* have fired a real-time Discord
webhook, then clusters that stream three complementary ways so we can see the
spam patterns before designing a coalescer.

The four per-event webhook types (all fire on ``post_save`` with ``created=True``)
are, from ``flipfix/apps/discord/webhook_handlers/``:

    log_entry_created            maintenance.LogEntry
    problem_report_created       maintenance.ProblemReport
    part_request_created         parts.PartRequest
    part_request_update_created  parts.PartRequestUpdate

We reconstruct "fired at" from each model's ``django-simple-history`` creation
row (``history_type='+'``) rather than the user-editable ``occurred_at``, so the
timeline reflects when records actually landed in the DB.

Caveats (see the plan in current_plan.md):

* ``sync-prod`` excludes ``discord_*`` tables, so we cannot replay the
  echo-suppression that prod applies to bot-originated records. Reconstructed
  counts are therefore an **upper bound**.
* Prod PII is scrubbed in dev, so we cluster on FK ids (the history actor), not
  names.

Nothing here touches production or writes any data; it only reads local history.
"""

from __future__ import annotations

import zoneinfo
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.maintenance.models import LogEntry, ProblemReport
from flipfix.apps.parts.models import PartRequest, PartRequestUpdate

# Event-type labels, in a stable display order.
EVENT_TYPES = ("log_entry", "problem_report", "part_request", "part_request_update")


@dataclass(frozen=True)
class Event:
    """One reconstructed "would-have-notified" event."""

    fired_at: datetime  # aware, UTC (from history_date)
    event_type: str
    actor_key: str  # unified grouping key, e.g. "u:42", "m:7", "anon"
    actor_label: str  # human-ish label for display
    machine_id: int | None
    machine_label: str
    summary: str


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


class StreamReconstructor:
    """Builds the unified creation-event stream from history tables.

    Actor keys are unified into User space where possible so that a maintainer's
    parts activity clusters together with their maintenance activity:

    * ``history_user_id`` (the authenticated user simple-history recorded) wins.
    * Else, for parts, resolve the Maintainer's linked ``user_id``.
    * Else fall back to the raw id in its own namespace, or ``anon``.
    """

    def __init__(self) -> None:
        self._machine_names: dict[int, str] = dict(
            MachineInstance.objects.values_list("id", "name")
        )
        # part_request_id -> machine_id, to attribute part-update events to a machine.
        self._request_machine: dict[int, int | None] = dict(
            PartRequest.objects.values_list("id", "machine_id")
        )
        # maintainer_id -> user_id, to unify parts actors into User space.
        self._maintainer_user: dict[int, int | None] = dict(
            Maintainer.objects.values_list("id", "user_id")
        )

    def _machine_label(self, machine_id: int | None) -> str:
        if machine_id is None:
            return "(no machine)"
        return self._machine_names.get(machine_id, f"machine#{machine_id}")

    def _actor_from_user(self, user_id: int | None) -> tuple[str, str]:
        if user_id is None:
            return "anon", "anonymous/system"
        return f"u:{user_id}", f"user#{user_id}"

    def _actor_from_maintainer(
        self, history_user_id: int | None, maintainer_id: int | None
    ) -> tuple[str, str]:
        if history_user_id is not None:
            return self._actor_from_user(history_user_id)
        if maintainer_id is not None:
            user_id = self._maintainer_user.get(maintainer_id)
            if user_id is not None:
                return self._actor_from_user(user_id)
            return f"m:{maintainer_id}", f"maintainer#{maintainer_id}"
        return "anon", "anonymous/system"

    def collect(self) -> list[Event]:
        events: list[Event] = []
        events.extend(self._log_entries())
        events.extend(self._problem_reports())
        events.extend(self._part_requests())
        events.extend(self._part_request_updates())
        events.sort(key=lambda e: e.fired_at)
        return events

    def _creations(self, model):
        """Iterate the creation (``history_type='+'``) rows of a model's history."""
        return model.history.filter(history_type="+").iterator()

    def _log_entries(self) -> list[Event]:
        out = []
        for h in self._creations(LogEntry):
            actor_key, actor_label = self._actor_from_user(h.history_user_id)
            text = (h.text or "").strip().replace("\n", " ")
            out.append(
                Event(
                    fired_at=h.history_date,
                    event_type="log_entry",
                    actor_key=actor_key,
                    actor_label=actor_label,
                    machine_id=h.machine_id,
                    machine_label=self._machine_label(h.machine_id),
                    summary=text[:80] or "(log entry)",
                )
            )
        return out

    def _problem_reports(self) -> list[Event]:
        out = []
        for h in self._creations(ProblemReport):
            # Problem reports are usually visitor-submitted; the history actor is
            # often null. Fall back to the reporting user where one exists.
            user_id = h.history_user_id or h.reported_by_user_id
            actor_key, actor_label = self._actor_from_user(user_id)
            out.append(
                Event(
                    fired_at=h.history_date,
                    event_type="problem_report",
                    actor_key=actor_key,
                    actor_label=actor_label,
                    machine_id=h.machine_id,
                    machine_label=self._machine_label(h.machine_id),
                    summary=h.get_problem_type_display(),
                )
            )
        return out

    def _part_requests(self) -> list[Event]:
        out = []
        for h in self._creations(PartRequest):
            actor_key, actor_label = self._actor_from_maintainer(
                h.history_user_id, h.requested_by_id
            )
            out.append(
                Event(
                    fired_at=h.history_date,
                    event_type="part_request",
                    actor_key=actor_key,
                    actor_label=actor_label,
                    machine_id=h.machine_id,
                    machine_label=self._machine_label(h.machine_id),
                    summary="part request",
                )
            )
        return out

    def _part_request_updates(self) -> list[Event]:
        out = []
        for h in self._creations(PartRequestUpdate):
            actor_key, actor_label = self._actor_from_maintainer(h.history_user_id, h.posted_by_id)
            machine_id = self._request_machine.get(h.part_request_id)
            status = f" → {h.new_status}" if h.new_status else ""
            out.append(
                Event(
                    fired_at=h.history_date,
                    event_type="part_request_update",
                    actor_key=actor_key,
                    actor_label=actor_label,
                    machine_id=machine_id,
                    machine_label=self._machine_label(machine_id),
                    summary=f"part update{status}",
                )
            )
        return out


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


@dataclass
class Cluster:
    events: list[Event]

    @property
    def size(self) -> int:
        return len(self.events)

    @property
    def start(self) -> datetime:
        return self.events[0].fired_at

    @property
    def end(self) -> datetime:
        return self.events[-1].fired_at

    @property
    def span(self) -> timedelta:
        return self.end - self.start

    @property
    def type_breakdown(self) -> Counter:
        return Counter(e.event_type for e in self.events)

    @property
    def actor_keys(self) -> set[str]:
        return {e.actor_key for e in self.events}

    @property
    def machine_ids(self) -> set[int | None]:
        return {e.machine_id for e in self.events}


def gap_clusters(events: list[Event], key_fn, gap: timedelta) -> list[Cluster]:
    """Session-cluster events sharing a key: a new cluster starts when the gap to
    the previous same-key event exceeds ``gap``."""
    by_key: dict[object, list[Event]] = defaultdict(list)
    for e in events:
        by_key[key_fn(e)].append(e)

    clusters: list[Cluster] = []
    for group in by_key.values():
        group.sort(key=lambda e: e.fired_at)
        current = [group[0]]
        for prev, cur in zip(group, group[1:], strict=False):
            if cur.fired_at - prev.fired_at <= gap:
                current.append(cur)
            else:
                clusters.append(Cluster(current))
                current = [cur]
        clusters.append(Cluster(current))
    return clusters


def global_peaks(events: list[Event], bucket: timedelta, min_peak: int) -> list[Cluster]:
    """Fixed wall-clock buckets holding at least ``min_peak`` events."""
    bucket_seconds = int(bucket.total_seconds())
    by_bucket: dict[int, list[Event]] = defaultdict(list)
    for e in events:
        slot = int(e.fired_at.timestamp()) // bucket_seconds
        by_bucket[slot].append(e)
    return [Cluster(evs) for evs in by_bucket.values() if len(evs) >= min_peak]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Reconstruct the historical Discord notification stream and cluster it "
        "(actor sessions, per-machine bursts, global peaks) to reveal spam patterns."
    )

    tz: zoneinfo.ZoneInfo

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--gap",
            type=int,
            default=10,
            help="Minutes of silence that end an actor/machine session (default 10).",
        )
        parser.add_argument(
            "--bucket",
            type=int,
            default=15,
            help="Minutes per fixed bucket for the global-peaks lens (default 15).",
        )
        parser.add_argument(
            "--min-peak",
            type=int,
            default=5,
            help="Minimum events in a bucket to count as a global peak (default 5).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=25,
            help="Show at most this many clusters per lens (default 25).",
        )
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help="Only include events on/after this ISO date (e.g. 2025-01-01).",
        )
        parser.add_argument(
            "--tz",
            type=str,
            default="America/Los_Angeles",
            help=(
                "Timezone for human-readable timestamps (default America/Los_Angeles). "
                "Clustering gaps are timezone-independent; this only affects display."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        gap = timedelta(minutes=options["gap"])
        bucket = timedelta(minutes=options["bucket"])
        min_peak: int = options["min_peak"]
        top: int = options["top"]

        try:
            self.tz = zoneinfo.ZoneInfo(options["tz"])
        except zoneinfo.ZoneInfoNotFoundError:
            self.stderr.write(f"Unknown timezone {options['tz']!r}; falling back to UTC.")
            self.tz = zoneinfo.ZoneInfo("UTC")

        events = StreamReconstructor().collect()

        if options["since"]:
            cutoff = timezone.make_aware(
                datetime.fromisoformat(options["since"]), zoneinfo.ZoneInfo("UTC")
            )
            events = [e for e in events if e.fired_at >= cutoff]

        if not events:
            self.stdout.write("No creation events found. Did you run `make sync-prod`?")
            return

        self._render_overview(events, gap, bucket, min_peak)

        # Lens A — actor sessions (one person's flurry of activity).
        actor_clusters = [
            c for c in gap_clusters(events, lambda e: e.actor_key, gap) if c.size >= 2
        ]
        self._render_lens(
            "LENS A — Actor sessions",
            f"Same actor, gap ≤ {options['gap']} min. Models example #1 "
            "(one person adds a machine, sets status, files reports…).",
            actor_clusters,
            top,
            show_actor=True,
        )

        # Lens B — per-machine bursts (one machine spamming the channel).
        machine_clusters = [
            c for c in gap_clusters(events, lambda e: e.machine_id, gap) if c.size >= 2
        ]
        self._render_lens(
            "LENS B — Per-machine bursts",
            f"Same machine, any actor, gap ≤ {options['gap']} min. "
            "Surfaces one machine flooding the feed.",
            machine_clusters,
            top,
            show_actor=False,
        )

        # Lens C — global peaks (raw firehose spikes).
        peak_clusters = global_peaks(events, bucket, min_peak)
        self._render_lens(
            "LENS C — Global peaks",
            f"Fixed {options['bucket']}-min buckets holding ≥ {min_peak} events, "
            "regardless of actor or machine.",
            peak_clusters,
            top,
            show_actor=False,
        )

    # -- rendering helpers --------------------------------------------------

    def _fmt(self, dt: datetime) -> str:
        return dt.astimezone(self.tz).strftime("%Y-%m-%d %H:%M")

    def _fmt_span(self, span: timedelta) -> str:
        minutes = int(span.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes}m"
        return f"{minutes // 60}h{minutes % 60:02d}m"

    def _fmt_breakdown(self, breakdown: Counter) -> str:
        return ", ".join(f"{t}×{breakdown[t]}" for t in EVENT_TYPES if breakdown.get(t))

    def _render_overview(
        self, events: list[Event], gap: timedelta, bucket: timedelta, min_peak: int
    ) -> None:
        by_type = Counter(e.event_type for e in events)
        actors = {e.actor_key for e in events}
        machines = {e.machine_id for e in events if e.machine_id is not None}

        w = self.stdout.write
        w("=" * 78)
        w("DISCORD NOTIFICATION STREAM — RECONSTRUCTED & CLUSTERED")
        w("=" * 78)
        w(f"Timezone for display: {self.tz}")
        w(
            f"Window: {self._fmt(events[0].fired_at)} → {self._fmt(events[-1].fired_at)} "
            f"({(events[-1].fired_at - events[0].fired_at).days} days)"
        )
        w("")
        w(f"Total would-have-fired notifications: {len(events)}")
        for t in EVENT_TYPES:
            if by_type.get(t):
                w(f"    {t:<22} {by_type[t]:>5}")
        w(f"Distinct actors: {len(actors)}    Distinct machines: {len(machines)}")
        w("")
        w("CAVEATS")
        w("  * Upper bound: discord_* tables are not synced, so prod's echo")
        w("    suppression of bot-originated records cannot be replayed here.")
        w("  * Actors are grouped by history user id (parts unified via Maintainer→user);")
        w("    PII is scrubbed in dev, so names are unavailable.")

    def _render_lens(
        self,
        title: str,
        subtitle: str,
        clusters: list[Cluster],
        top: int,
        show_actor: bool,
    ) -> None:
        clusters = sorted(clusters, key=lambda c: c.size, reverse=True)

        w = self.stdout.write
        w("")
        w("=" * 78)
        w(title)
        w("-" * 78)
        w(subtitle)
        w("")

        if not clusters:
            w("  (no clusters)")
            return

        collapsible = sum(c.size for c in clusters)
        saved = collapsible - len(clusters)
        w(
            f"{len(clusters)} clusters covering {collapsible} notifications. "
            f"Collapsing each to one message would remove {saved} "
            f"({self._pct(saved, collapsible)})."
        )

        size_hist = Counter(c.size for c in clusters)
        hist_str = "  ".join(
            f"{size}:{count}" for size, count in sorted(size_hist.items(), reverse=True)
        )
        w(f"Cluster-size distribution (size:count): {hist_str}")
        w("")

        shown = clusters[:top]
        for i, c in enumerate(shown, 1):
            self._render_cluster(i, c, show_actor)
        if len(clusters) > top:
            w(f"  … {len(clusters) - top} smaller clusters not shown (raise --top to see).")

    def _render_cluster(self, index: int, c: Cluster, show_actor: bool) -> None:
        w = self.stdout.write
        machines = [m for m in c.machine_ids if m is not None]
        machine_labels = {e.machine_label for e in c.events}
        if len(machine_labels) == 1:
            machine_str = next(iter(machine_labels))
        else:
            machine_str = f"{len(machines)} machines"

        actor_str = ""
        if show_actor:
            labels = {e.actor_label for e in c.events}
            actor_str = next(iter(labels)) if len(labels) == 1 else f"{len(labels)} actors"
        else:
            actor_str = f"{len(c.actor_keys)} actor(s)"

        w(
            f"#{index:<3} size {c.size:>3}  {self._fmt(c.start)}  span {self._fmt_span(c.span):>6}"
            f"  {actor_str}  |  {machine_str}"
        )
        w(f"       {self._fmt_breakdown(c.type_breakdown)}")

    @staticmethod
    def _pct(part: int, whole: int) -> str:
        if not whole:
            return "0%"
        return f"{100 * part / whole:.0f}%"
