"""Replay the historical notification stream through the coalescer.

Dev-only. Writes ``discord_coalescing_cases.md``: the evidence document behind the
notification-coalescing rework. That output is deliberately left untracked — it
reproduces real maintainer usernames and the text of real reports, and this
repository is public. Every "input" it prints is a real
record from the local (sanitized production) database, and every "output" is the
payload the *live* coalescing code builds for it — this command calls
:func:`~flipfix.apps.discord.tasks.build_pending_posts`, the same function the
scheduled flush uses, rather than reimplementing the rendering. Change the
formatter and re-run this to see what the channel would look like.

What it reconstructs, and what it cannot:

* Events come from each model's ``django-simple-history`` creation row
  (``history_type='+'``), the same basis as ``analyze_notification_clusters``.
  That is when the record actually landed, not the user-editable ``occurred_at``.
* Buffering follows :func:`~flipfix.apps.discord.tasks.dispatch_webhook`: skip
  records marked ``announce=False``, key the buffer on
  ``handler.get_submitting_user()``, and post immediately when that is ``None``.
* ``sync-prod`` excludes the ``discord_*`` tables, so the echo-suppression prod
  applies to bot-originated records cannot be replayed. Counts are an upper bound.
* The flush runs once a minute in production, so a real post lands up to 60
  seconds after the due time computed here.

Nothing here writes to the database or contacts Discord; it only reads history.
"""

from __future__ import annotations

import zoneinfo
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

# override_settings is a test helper, but it is exactly the scoped, restoring
# setting override this command needs for SITE_URL.
from django.test.utils import override_settings

from flipfix.apps.discord.models import PendingNotification
from flipfix.apps.discord.tasks import (
    COALESCE_MAX_WAIT,
    COALESCE_QUIET_PERIOD,
    MAX_RICH_POSTS_PER_FLUSH,
    build_pending_posts,
)
from flipfix.apps.discord.webhook_handlers import WebhookHandler, get_webhook_handler
from flipfix.apps.maintenance import auto_log

# The four per-event webhook types, in a stable display order.
HANDLER_NAMES = ("log_entry", "problem_report", "part_request", "part_request_update")

# How wide a text cell gets before it is trimmed in the input tables.
CELL_WIDTH = 90

# How many "before" messages to render in full before summarising the rest.
MAX_BEFORE_SAMPLES = 4

# The window Case 10 scans for overlapping sessions.
BUSY_WINDOW = timedelta(minutes=40)


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayEvent:
    """One record creation that would have fired a webhook."""

    handler: WebhookHandler
    obj: Any
    fired_at: datetime
    # The buffer's grouping key: who saved the record. None => posts immediately.
    actor: Any | None
    # The pre-rework grouping key — what the shipped ``get_actor_user()``
    # returned — kept only so the before/after table can show how much of the
    # stream that key treated as anonymous.
    attributed: Any | None

    @property
    def machine(self) -> Any | None:
        return self.handler.get_machine(self.obj)

    @property
    def record_label(self) -> str:
        """How the input tables name this record, e.g. "log entry (auto: status change)"."""
        if self.handler.name != "log_entry":
            return self.handler.name.replace("_", " ")
        recognised = auto_log.classify(self.obj.text)
        if recognised is None:
            return "log entry (typed by hand)"
        return f"log entry (auto: {_AUTO_LOG_LABELS[recognised.kind]})"


# What the input tables call each kind of Flipfix-written log entry. "Moved to
# the floor" is a location change wearing a party hat, so it reads as one.
_AUTO_LOG_LABELS = {
    auto_log.AutoLogKind.MACHINE_ADDED: "machine added",
    auto_log.AutoLogKind.STATUS_CHANGED: "status change",
    auto_log.AutoLogKind.LOCATION_CHANGED: "location change",
    auto_log.AutoLogKind.MOVED_TO_FLOOR: "location change",
    auto_log.AutoLogKind.REPORT_CLOSED: "report closed",
    auto_log.AutoLogKind.REPORT_REOPENED: "report re-opened",
}


def collect_events() -> tuple[list[ReplayEvent], list[ReplayEvent]]:
    """Rebuild the would-have-fired event stream, newest last.

    Returns the events that still announce, and separately those suppressed by
    ``announce=False`` (the intake checklists). The suppressed ones never reach
    the channel now, but the pre-rework code posted them, so the before/after
    comparison has to count them.
    """
    events: list[ReplayEvent] = []
    suppressed: list[ReplayEvent] = []

    for name in HANDLER_NAMES:
        handler = get_webhook_handler(name)
        if handler is None:  # pragma: no cover - registry is populated at startup
            raise CommandError(f"No webhook handler registered as {name!r}")
        model = handler.get_model_class()

        # One query for the objects, with the handler's own select/prefetch, so
        # rendering below doesn't fan out into per-record lookups.
        queryset = model.objects.all()
        if handler.select_related:
            queryset = queryset.select_related(*handler.select_related)
        if handler.prefetch_related:
            queryset = queryset.prefetch_related(*handler.prefetch_related)
        objects = {obj.pk: obj for obj in queryset}

        # The creation history row is when the record landed. A record can only
        # be created once, so the first row per id is the one we want.
        fired: dict[int, datetime] = {}
        for object_id, history_date in (
            model.history.filter(history_type="+")
            .order_by("history_date")
            .values_list("id", "history_date")
        ):
            fired.setdefault(object_id, history_date)

        for object_id, fired_at in fired.items():
            obj = objects.get(object_id)
            if obj is None:  # deleted since; it can never be delivered
                continue
            event = ReplayEvent(
                handler=handler,
                obj=obj,
                fired_at=fired_at,
                actor=handler.get_submitting_user(obj),
                attributed=(
                    obj.created_by
                    if handler.name == "log_entry"
                    else handler.get_attributed_user(obj)
                ),
            )
            target = events if handler.should_announce(object_id) else suppressed
            target.append(event)

    events.sort(key=lambda event: event.fired_at)
    suppressed.sort(key=lambda event: event.fired_at)
    return events, suppressed


# ---------------------------------------------------------------------------
# Buffering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Batch:
    """One actor's events that the flush would post together."""

    actor: Any
    events: list[ReplayEvent]
    flush_at: datetime
    capped: bool  # closed by the max-wait cap rather than by the actor going quiet

    @property
    def held_for(self) -> timedelta:
        return self.flush_at - self.events[0].fired_at

    @property
    def reason(self) -> str:
        held = int(self.held_for.total_seconds() // 60)
        label = "max-wait cap" if self.capped else "quiet period"
        return f"{label}, {held}m after its first event"


def _close(events: Sequence[ReplayEvent]) -> Batch:
    """Close a run of events, working out when and why the flush would fire."""
    cap_at = events[0].fired_at + COALESCE_MAX_WAIT
    quiet_at = events[-1].fired_at + COALESCE_QUIET_PERIOD
    flush_at = min(cap_at, quiet_at)
    return Batch(
        actor=events[0].actor,
        events=list(events),
        flush_at=flush_at,
        capped=flush_at == cap_at,
    )


def batch_by_actor(events: Sequence[ReplayEvent]) -> list[Batch]:
    """Split the buffered events into the batches the debounced flush would make.

    Mirrors :func:`~flipfix.apps.discord.tasks.flush_pending_notifications`: an
    actor's buffer is due once they have been quiet for ``COALESCE_QUIET_PERIOD``
    or the oldest event has waited ``COALESCE_MAX_WAIT``, whichever comes first.
    Anything that arrives after that moment belongs to the next batch.
    """
    per_actor: dict[Any, list[ReplayEvent]] = defaultdict(list)
    for event in events:
        if event.actor is None:  # nobody signed in: posts immediately, never buffered
            continue
        per_actor[event.actor.pk].append(event)

    batches: list[Batch] = []
    for actor_events in per_actor.values():
        current: list[ReplayEvent] = []
        for event in actor_events:
            if current:
                due_at = min(
                    current[0].fired_at + COALESCE_MAX_WAIT,
                    current[-1].fired_at + COALESCE_QUIET_PERIOD,
                )
                if event.fired_at >= due_at:
                    batches.append(_close(current))
                    current = []
            current.append(event)
        if current:
            batches.append(_close(current))

    batches.sort(key=lambda batch: batch.flush_at)
    return batches


# ---------------------------------------------------------------------------
# Rendering the messages
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """A rendered Discord message and when it would land."""

    posted_at: datetime
    payload: dict
    actor_label: str

    @property
    def title(self) -> str:
        return self.payload["embeds"][0].get("title", "")

    @property
    def description(self) -> str:
        return self.payload["embeds"][0].get("description", "")

    @property
    def photo_count(self) -> int:
        return sum(1 for embed in self.payload["embeds"] if embed.get("image"))


def posts_for(batch: Batch) -> list[Message]:
    """Render a batch through the live coalescer."""
    rows = []
    for index, event in enumerate(batch.events):
        row = PendingNotification(
            handler_name=event.handler.name,
            object_id=event.obj.pk,
            actor=event.actor,
        )
        # build_pending_posts reports the rows each message covers by pk; these
        # rows are never saved, so give them synthetic ones.
        row.pk = index
        rows.append(row)

    posts, _orphans = build_pending_posts(rows)
    label = actor_label(batch.actor)
    return [
        Message(posted_at=batch.flush_at, payload=post.payload, actor_label=label) for post in posts
    ]


def immediate_message(event: ReplayEvent) -> Message:
    """Render an unbuffered event — nobody was signed in, so it posts as it happens."""
    return Message(
        posted_at=event.fired_at,
        payload=event.handler.format_webhook_message(event.obj),
        actor_label="(nobody signed in)",
    )


def render_payload(payload: dict) -> str:
    """Show a webhook payload the way it reads in Discord."""
    embeds = payload["embeds"]
    main = embeds[0]
    lines = [f"TITLE  {main.get('title', '')}"]
    if main.get("url"):
        lines.append(f"LINK   {main['url']}")
    lines.append("BODY")
    description = main.get("description", "")
    lines.extend(f"  {line}" if line.strip() else "" for line in description.split("\n"))
    photos = sum(1 for embed in embeds if embed.get("image"))
    if photos:
        lines.append(f"IMAGES {photos} photo embed(s)")
    lines.append(f"[{len(description)} chars, {len(description.split())} words in body]")
    return "\n".join(lines)


def actor_label(user: Any) -> str:
    """Name an actor for the prose. Dev data is scrubbed, so this is a username."""
    if user is None:
        return "nobody signed in"
    return user.get_username()


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseSpec:
    """A case to illustrate, and how to find it in the replayed stream.

    ``pick`` returns the batches the case covers — usually one, but a session
    long enough to trip the max-wait cap is split across several and only makes
    sense read together.
    """

    title: str
    blurb: str
    pick: Callable[[list[Batch]], list[Batch]]


def _best(batches: list[Batch], key, where=None) -> list[Batch]:
    """Highest-scoring batch, breaking ties on the earliest one for stability."""
    candidates = [b for b in batches if where is None or where(b)]
    if not candidates:
        return []
    return [max(candidates, key=lambda b: (key(b), -b.flush_at.timestamp()))]


def sessions(batches: list[Batch]) -> list[list[Batch]]:
    """Group batches back into unbroken work sessions.

    The max-wait cap can close a buffer while its author is still working, so one
    continuous session shows up as several batches. Those belong together in the
    document: splitting a session across two messages is the behaviour worth
    seeing, not two unrelated bursts.
    """
    per_actor: dict[Any, list[Batch]] = defaultdict(list)
    for batch in batches:
        per_actor[batch.actor.pk].append(batch)

    grouped: list[list[Batch]] = []
    for actor_batches in per_actor.values():
        actor_batches.sort(key=lambda b: b.flush_at)
        run = [actor_batches[0]]
        for batch in actor_batches[1:]:
            gap = batch.events[0].fired_at - run[-1].events[-1].fired_at
            if gap < COALESCE_QUIET_PERIOD:
                run.append(batch)
            else:
                grouped.append(run)
                run = [batch]
        grouped.append(run)
    return grouped


def _biggest_session(batches: list[Batch]) -> list[Batch]:
    """The longest unbroken run of one person's activity."""
    runs = sessions(batches)
    if not runs:
        return []
    return max(runs, key=lambda run: sum(len(b.events) for b in run))


def _machines(batch: Batch) -> set[Any]:
    return {m.pk for e in batch.events if (m := e.machine) is not None}


def _substantive(batch: Batch) -> list[ReplayEvent]:
    return [e for e in batch.events if e.handler.is_substantive(e.obj)]


def _photo_total(batch: Batch) -> int:
    return sum(len(e.handler.get_photos(e.obj)) for e in batch.events)


def _longest_body(batch: Batch) -> int:
    return max(
        (
            len(e.handler.format_webhook_message(e.obj)["embeds"][0]["description"].split())
            for e in _substantive(batch)
        ),
        default=0,
    )


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        title="Bulk import — the biggest burst in the history",
        blurb=(
            "The largest unbroken run of records one person ever produced: the case the "
            "coalescer was built for. It is long enough that the 15-minute cap fires "
            "mid-session, so the buffer closes and reopens while they are still working."
        ),
        pick=_biggest_session,
    ),
    CaseSpec(
        title="Auto-log fan-out on one machine",
        blurb=(
            "One person works on a single machine; the `create_auto_log_entries` signal turns "
            "that into several log entries. The motivating example from the TODO — and what "
            "the rework is for: the repair note leads, and the bookkeeping follows it."
        ),
        pick=lambda bs: _best(
            bs,
            lambda b: len(b.events),
            where=lambda b: len(_machines(b)) == 1 and _substantive(b),
        ),
    ),
    CaseSpec(
        title="One person, many machines in one stretch",
        blurb=(
            "The same short entry written on machine after machine. Each is something a person "
            "typed on its own machine, so by the grouping rule each would earn its own post — "
            "this is that rule's worst case. It is also the one session in the whole history "
            "wide enough to trip the four-post cap, so the tail collapses into a summary."
        ),
        pick=lambda bs: _best(
            bs,
            lambda b: len(_machines(b)),
            where=lambda b: len(b.events) > 1 and len(_substantive(b)) == len(b.events),
        ),
    ),
    CaseSpec(
        title="Receiving parts",
        blurb=(
            "Several parts arrive together and get marked off in one sitting. Bare status "
            "flips carry nothing worth a post each, so they collapse into one summary."
        ),
        pick=lambda bs: _best(
            bs,
            lambda b: len(b.events),
            where=lambda b: len(b.events) > 1
            and all(e.handler.name.startswith("part_") for e in b.events),
        ),
    ),
    CaseSpec(
        title="Mixed session — repairs plus routine record-keeping",
        blurb=(
            "The shape the grouping rule exists for: work on more than one machine, plus a "
            "tail of status flips. Each machine with real content gets its own post; "
            "everything else merges into a single sweep."
        ),
        pick=lambda bs: _best(
            bs,
            lambda b: len(_machines(b)),
            where=lambda b: len(_substantive(b)) >= 2 and len(_substantive(b)) < len(b.events),
        ),
    ),
    CaseSpec(
        title="A batch with photos",
        blurb=(
            "Photos are a large part of what makes these posts useful. The gallery is "
            "gathered from the whole session, not just the leading record, so a photo on a "
            "follow-up entry still shows. Discord displays at most four."
        ),
        pick=lambda bs: _best(bs, _photo_total, where=lambda b: len(b.events) > 1),
    ),
    CaseSpec(
        title="The minimum coalesce — exactly two events",
        blurb=(
            "Two records, two different machines. Grouping is per machine, so this stays two "
            "posts: two machines touched is two pieces of news, not one digest."
        ),
        pick=lambda bs: _best(
            bs,
            lambda b: _longest_body(b),
            where=lambda b: len(b.events) == 2 and len(_machines(b)) == 2,
        ),
    ),
    CaseSpec(
        title="Long text — the write-up the old digest threw away",
        blurb=(
            "The longest hand-written entry in the history. The old digest reduced this to an "
            "80-character link line; the 500-word cap now lets it through whole."
        ),
        pick=lambda bs: _best(bs, _longest_body, where=lambda b: len(b.events) > 1),
    ),
    CaseSpec(
        title="A lone event — delayed five minutes for no benefit",
        blurb=(
            "One record, no burst. Coalescing still holds it for the full quiet period before "
            "posting the same message it would have posted immediately. This is the single "
            "most common outcome of the whole feature."
        ),
        pick=lambda bs: _best(bs, _photo_total, where=lambda b: len(b.events) == 1),
    ),
)


class Command(BaseCommand):
    help = "Replay the historical Discord notification stream and regenerate the cases document."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--output",
            default="discord_coalescing_cases.md",
            help="Where to write the document (default: discord_coalescing_cases.md).",
        )
        parser.add_argument(
            "--site-url",
            default="https://flipfix.theflip.museum",
            help=(
                "Base URL to render links against. Dev has no SITE_URL, and the document is "
                "about what production would post."
            ),
        )
        parser.add_argument(
            "--tz",
            default="America/Los_Angeles",
            help=(
                "Timezone for displayed timestamps (default America/Los_Angeles, matching "
                "analyze_notification_clusters). Buffering is timezone-independent; this "
                "only affects display."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            tz = zoneinfo.ZoneInfo(options["tz"])
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise CommandError(f"Unknown timezone: {options['tz']}") from exc

        # The formatters build absolute URLs from SITE_URL, which dev leaves
        # empty, and this document is about what production would post. Scope the
        # override so the command doesn't leave the setting changed behind it.
        with override_settings(SITE_URL=options["site_url"]):
            document = self._replay(tz)

        path = Path(options["output"])
        path.write_text(document, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {path} ({len(document.splitlines())} lines)"))

    def _replay(self, tz: zoneinfo.ZoneInfo) -> str:
        """Rebuild the stream, run it through the coalescer, and render the document."""
        self.stdout.write("Reconstructing the event stream…")
        events, suppressed = collect_events()
        if not events:
            raise CommandError(
                "No events found. Run `make db-up && scripts/sync_prod.sh --yes` first."
            )

        unbuffered = [e for e in events if e.actor is None]
        batches = batch_by_actor([e for e in events if e.actor is not None])

        self.stdout.write(f"{len(events)} events, {len(batches)} batches; rendering messages…")
        rendered: dict[int, list[Message]] = {id(b): posts_for(b) for b in batches}

        return self._render_document(
            events=events,
            unbuffered=unbuffered,
            batches=batches,
            rendered=rendered,
            immediate=[immediate_message(e) for e in unbuffered],
            suppressed=suppressed,
            tz=tz,
        )

    # -- document sections -------------------------------------------------

    def _render_document(
        self,
        *,
        events: list[ReplayEvent],
        unbuffered: list[ReplayEvent],
        batches: list[Batch],
        rendered: dict[int, list[Message]],
        immediate: list[Message],
        suppressed: list[ReplayEvent],
        tz: zoneinfo.ZoneInfo,
    ) -> str:
        self._tz = tz
        total_messages = sum(len(rendered[id(b)]) for b in batches) + len(immediate)

        out: list[str] = []
        out.append(_INTRO)
        out.append(self._numbers(events, unbuffered, batches, rendered, total_messages, suppressed))

        chosen: list[tuple[CaseSpec, list[Batch]]] = []
        used: set[int] = set()
        for spec in CASES:
            group = spec.pick([b for b in batches if id(b) not in used])
            if not group:
                self.stdout.write(self.style.WARNING(f"No batch matched case: {spec.title}"))
                continue
            used.update(id(batch) for batch in group)
            chosen.append((spec, group))

        for index, (spec, group) in enumerate(chosen, start=1):
            out.append(self._case(index, spec, group, rendered))

        out.append(self._busy_stretch(len(chosen) + 1, batches, rendered, immediate))
        out.append(
            self._comparison(
                events, unbuffered, batches, total_messages, suppressed, chosen, rendered
            )
        )
        out.append(_HOW_PRODUCED)
        return "\n".join(out)

    def _fmt(self, moment: datetime) -> str:
        return moment.astimezone(self._tz).strftime("%Y-%m-%d %H:%M:%S")

    def _clock(self, moment: datetime) -> str:
        return moment.astimezone(self._tz).strftime("%H:%M:%S")

    def _numbers(
        self,
        events: list[ReplayEvent],
        unbuffered: list[ReplayEvent],
        batches: list[Batch],
        rendered: dict[int, list[Message]],
        total_messages: int,
        suppressed: list[ReplayEvent],
    ) -> str:
        span_days = (events[-1].fired_at - events[0].fired_at).days
        sizes = Counter(len(b.events) for b in batches)
        multi = [b for b in batches if len(b.events) > 1]
        multi_messages = sum(len(rendered[id(b)]) for b in multi)
        multi_records = sum(len(b.events) for b in multi)
        capped = sum(1 for b in batches if b.capped)
        mix = Counter(e.handler.name for e in events)
        anon_mix = Counter(e.handler.name for e in unbuffered)
        held = sum((b.held_for.total_seconds() for b in batches), 0.0) / max(len(batches), 1)
        reduction = 100 - round(total_messages / len(events) * 100)

        size_list = ", ".join(f"`{size}`×{count}" for size, count in sorted(sizes.items()))
        anon_list = ", ".join(
            f"`{name}` {count}/{mix[name]}" for name, count in sorted(anon_mix.items())
        )

        lines = [
            "## The stream, in numbers",
            "",
            f"- **{len(events)}** would-have-fired notifications over **{span_days}** days "
            f"({self._fmt(events[0].fired_at)} → {self._fmt(events[-1].fired_at)}).",
            f"- Under coalescing that becomes **{total_messages}** messages — "
            f"**{reduction}% fewer posts**.",
            f"- **{len(unbuffered)}** of those messages come from records with no logged-in "
            "actor (visitor problem reports, and parts records with no requester) — they "
            "never batch.",
            f"- Buffered batches by size: {size_list}",
            f"- **{len(multi)}** buffers hold more than one record; "
            f"**{sizes.get(1, 0)}** are single records that get delayed by the quiet period "
            "and post unchanged.",
            f"- Multi-record buffers produce **{multi_messages}** messages from "
            f"**{multi_records}** records.",
            f"- **{capped}** batches were closed by the 15-minute cap rather than by the "
            "actor going quiet.",
            f"- **{len(suppressed)}** records were never announced at all — the ones marked "
            "`announce=False` (the intake checklists).",
            "",
            "Event mix: " + ", ".join(f"`{n}` {c}" for n, c in mix.most_common()),
            "",
            f"Events with **no logged-in actor** (these bypass the buffer entirely): "
            f"{anon_list} — **{len(unbuffered)} of {len(events)}** events, "
            f"{round(len(unbuffered) / len(events) * 100)}% of the stream.",
            "",
            f"Average delay for a buffered message: **{held / 60:.1f} minutes** after its "
            "first event.",
            "",
            _CAVEATS,
            "",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _case(
        self,
        index: int,
        spec: CaseSpec,
        group: list[Batch],
        rendered: dict[int, list[Message]],
    ) -> str:
        events = [event for batch in group for event in batch.events]
        messages = [m for batch in group for m in rendered[id(batch)]]
        span = int((events[-1].fired_at - events[0].fired_at).total_seconds() // 60)

        out = [
            f"## Case {index} — {spec.title}",
            "",
            spec.blurb,
            "",
            f"**Actor:** `{actor_label(group[0].actor)}` · **Window:** "
            f"{self._fmt(events[0].fired_at)} → {self._fmt(events[-1].fired_at)} "
            f"({span}m span)",
            "",
            f"### Input — {_plural(len(events), 'record')}",
            "",
        ]
        for batch in group:
            # A session split by the cap is clearer as one table per buffer.
            if len(group) > 1:
                out += [f"_Buffer flushed {self._clock(batch.flush_at)} — {batch.reason}:_", ""]
            out += ["| # | time | machine | record | text |", "| --- | --- | --- | --- | --- |"]
            for number, event in enumerate(batch.events, start=1):
                machine = event.machine
                out.append(
                    f"| {number} | {self._clock(event.fired_at)} "
                    f"| {_cell(machine.short_display_name if machine else '—', 40)} "
                    f"| {event.record_label} "
                    f"| {_cell(event.handler.get_summary_line(event.obj))} |"
                )
            out.append("")

        before = [
            Message(
                posted_at=event.fired_at,
                payload=event.handler.format_webhook_message(event.obj),
                actor_label=actor_label(group[0].actor),
            )
            for event in events
        ]
        out += [f"### Output BEFORE coalescing — {len(before)} separate Discord messages", ""]
        for number, message in enumerate(before[:MAX_BEFORE_SAMPLES], start=1):
            out += [
                f"> **posted {self._clock(message.posted_at)} — message {number} of {len(before)}**",
                "",
                "```text",
                render_payload(message.payload),
                "```",
                "",
            ]
        if len(before) > MAX_BEFORE_SAMPLES:
            remaining = len(before) - MAX_BEFORE_SAMPLES
            out += [f"> …and {_plural(remaining, 'more message')} of the same shape.", ""]

        out += [f"### Output AFTER coalescing — {_plural(len(messages), 'message')}", ""]
        number = 0
        for batch in group:
            for message in rendered[id(batch)]:
                number += 1
                out += [
                    f"> **posted {self._clock(message.posted_at)} — message {number} of "
                    f"{len(messages)} ({batch.reason})**",
                    "",
                    "```text",
                    render_payload(message.payload),
                    "```",
                    "",
                ]

        photos_before = sum(m.photo_count for m in before)
        photos_after = sum(m.photo_count for m in messages)
        if photos_before or photos_after:
            out += [
                f"> 📷 {photos_before} photo embed(s) before, **{photos_after} after**.",
                "",
            ]
        out += ["---", ""]
        return "\n".join(out)

    def _busy_stretch(
        self,
        index: int,
        batches: list[Batch],
        rendered: dict[int, list[Message]],
        immediate: list[Message],
    ) -> str:
        """The channel as a reader sees it: several people's sessions landing together."""
        everything = sorted(
            [m for b in batches for m in rendered[id(b)]] + immediate,
            key=lambda m: m.posted_at,
        )
        # Widest variety of voices inside one window is the most illustrative.
        best_start, best_actors = 0, 0
        for start in range(len(everything)):
            end = start
            while (
                end < len(everything)
                and everything[end].posted_at - everything[start].posted_at <= BUSY_WINDOW
            ):
                end += 1
            actors = len({m.actor_label for m in everything[start:end]})
            if actors > best_actors:
                best_start, best_actors = start, actors
        window = [
            m
            for m in everything[best_start:]
            if m.posted_at - everything[best_start].posted_at <= BUSY_WINDOW
        ]

        out = [
            f"## Case {index} — A busy stretch — several people at once",
            "",
            "Coalescing is per-actor, so overlapping sessions still interleave: the reader "
            "sees several people's messages land together, each summarising a window that "
            "has already closed. This is the channel as a reader experiences it, rather "
            "than one batch in isolation.",
            "",
            f"**Window:** {self._fmt(window[0].posted_at)} → {self._fmt(window[-1].posted_at)} "
            f"· **{best_actors} people**",
            "",
            "### Output — the channel, in the order Discord shows it",
            "",
            "| posted | actor | message |",
            "| --- | --- | --- |",
        ]
        for message in window:
            out.append(
                f"| {self._clock(message.posted_at)} | `{message.actor_label}` "
                f"| {_cell(message.title, 60)} |"
            )
        out += ["", "---", ""]
        return "\n".join(out)

    def _comparison(
        self,
        events: list[ReplayEvent],
        unbuffered: list[ReplayEvent],
        batches: list[Batch],
        total_messages: int,
        suppressed: list[ReplayEvent],
        chosen: list[tuple[CaseSpec, list[Batch]]],
        rendered: dict[int, list[Message]],
    ) -> str:
        """Compare the shipped per-actor digest with the per-machine rework.

        The old digest keyed the buffer on the record's *attribution* field and
        emitted exactly one message per batch, so both of its numbers can be
        recomputed from the same stream without resurrecting the old code.
        """
        old_stream = sorted(events + suppressed, key=lambda e: e.fired_at)
        old_anonymous = [e for e in old_stream if e.attributed is None]
        old_buffered = [e for e in old_stream if e.attributed is not None]
        old_batches = _batch_on(old_buffered, key=lambda e: e.attributed.pk)
        old_messages = len(old_batches) + len(old_anonymous)

        rows = [
            ("Messages posted", str(old_messages), f"**{total_messages}**"),
            (
                "Reduction vs. no coalescing",
                f"{100 - round(old_messages / len(old_stream) * 100)}%",
                f"**{100 - round(total_messages / len(events) * 100)}%**",
            ),
            (
                'Events that skipped the buffer as "anonymous"',
                str(len(old_anonymous)),
                f"**{len(unbuffered)}**",
            ),
            ("Intake checklists posted", str(len(suppressed)), "**0**"),
            ("Body text in a merged post", "80 characters", "**up to 500 words**"),
        ]

        out = [
            "## What the rework changed",
            "",
            "Measured on the same days of production records, before and after. The "
            '"before" column is the shipped per-actor digest: it keyed the buffer on each '
            "record's attribution field and emitted exactly one message per batch, so both "
            "of its numbers are recomputable from this same stream. Each column is measured "
            "against the events its own regime would post — the rework suppresses the "
            f"{len(suppressed)} intake checklists the old code announced, so its baseline is "
            f"{len(events)} events against the old {len(old_stream)}.",
            "",
            "| | Before (per-actor digest) | After (per-machine session) |",
            "| --- | ---: | ---: |",
        ]
        out += [f"| {label} | {before} | {after} |" for label, before, after in rows]
        out += [
            "",
            "The message count barely moves, which is the point: the old digest was quiet "
            "because it threw content away. The same volume now carries the repair notes "
            "and the photos.",
            "",
            "Case by case:",
            "",
        ]
        for index, (spec, group) in enumerate(chosen, start=1):
            records = sum(len(batch.events) for batch in group)
            count = sum(len(rendered[id(batch)]) for batch in group)
            out.append(
                f"- **Case {index}** ({spec.title}) — {_plural(records, 'record')} → "
                f"{_plural(count, 'message')}."
            )
        out += ["", self._tension(batches), "", "---", ""]
        return "\n".join(out)

    def _tension(self, batches: list[Batch]) -> str:
        """The cost of the per-machine rule, and how often the cap has to step in."""
        hit = demoted = 0
        for batch in batches:
            written = {
                (event.machine.pk if event.machine is not None else None)
                for event in batch.events
                if event.handler.is_substantive(event.obj)
            }
            if len(written) > MAX_RICH_POSTS_PER_FLUSH:
                hit += 1
                demoted += len(written) - MAX_RICH_POSTS_PER_FLUSH

        return f"""### The tension worth knowing about

Grouping per machine means somebody who writes a genuine entry on many machines in one
stretch gets a post for each of them. That rule is right for real repair work — two
machines fixed should read as two pieces of news — but its worst case is a copy-paste
session of identical one-liners.

The {MAX_RICH_POSTS_PER_FLUSH}-post cap bounds it: past that many machines the rest join the summary message,
and the machines with the most written about them are the ones that keep their own post.
Over these {len(batches)} buffers the cap fires **{_plural(hit, "time")}**, demoting
**{_plural(demoted, "machine")}** — a safety valve rather than a routine behaviour.

What it costs when it fires: a summary line names the machine but carries no body text, so
a demoted entry loses its wording. That is the deliberate trade — bounded volume, at the
price of the shortest notes in an unusually wide session.

### Also worth noting

- Most buffers still hold a **single record** and are delayed five minutes for no merging
  benefit. That delay is what lets a follow-up status change land in the same post, and a
  modest delay was called acceptable, so it stays.
- **Attribution is unchanged.** The post still credits the person the record is about even
  when somebody else saved it; only the _grouping_ moved to the saver.
- Posts reading "— Anonymous" do so because the dev copy scrubs free-text reporter names.
  Production shows the real name."""


def _batch_on(events: Sequence[ReplayEvent], *, key) -> list[list[ReplayEvent]]:
    """Group events into debounced batches on an arbitrary actor key.

    Used to recompute what the pre-rework, attribution-keyed buffer would have done.
    """
    per_key: dict[Any, list[ReplayEvent]] = defaultdict(list)
    for event in events:
        per_key[key(event)].append(event)

    batches: list[list[ReplayEvent]] = []
    for grouped in per_key.values():
        current: list[ReplayEvent] = []
        for event in grouped:
            if current:
                due_at = min(
                    current[0].fired_at + COALESCE_MAX_WAIT,
                    current[-1].fired_at + COALESCE_QUIET_PERIOD,
                )
                if event.fired_at >= due_at:
                    batches.append(current)
                    current = []
            current.append(event)
        if current:
            batches.append(current)
    return batches


def _plural(count: int, noun: str) -> str:
    """ "1 record" / "12 records" — the tables and headings read as prose."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _cell(text: str, width: int = CELL_WIDTH) -> str:
    """Flatten text onto one line and trim it to fit a Markdown table cell."""
    flat = " ".join((text or "").split()).replace("|", "\\|")
    return flat if len(flat) <= width else flat[:width].rstrip() + "…"


_INTRO = """# Discord notification coalescing — real cases

Generated by `manage.py replay_notification_coalescing`, which replays the **real production
notification stream** (synced via `make sync-prod`) through the live coalescing code in
`flipfix/apps/discord/tasks.py` and `formatters.py`. Every "input" below is an actual record;
every "output" is the actual webhook payload the current code produces for it, rendered as it
would read in Discord. Re-run the command after changing the formatter to see what moves.

## How it works

- Events are buffered per **person who saved the record** (the `django-simple-history` creation
  user, not the attribution field). A buffer flushes after **5 minutes of quiet**, or **15
  minutes** after the first event, whichever comes first.
- Events with nobody signed in — the public QR problem report flow — skip the buffer and post
  immediately.
- Records marked "don't announce" (an intake checklist) never post at all.
- The buffer is grouped **by machine**. A group containing something a person wrote becomes a
  full post: their text (up to 500 words), the session's photos, and the rest of that machine's
  records listed underneath.
- Groups holding nothing but recorded actions (status flips, moves) merge into **one** summary
  message grouped by action.
- At most **four** full posts come out of one flush. Past that, the machines with the least
  written about them give up their own post and join the summary instead.

"""

_CAVEATS = """> Caveats: `sync-prod` excludes `discord_*` tables, so Discord-originated records that prod
> suppresses as echoes still appear here (counts are an upper bound, and some of the actor-less
> parts records below are probably Discord-created and never actually posted). Free-text names
> are scrubbed in the dev copy — the actor foreign keys are not — so actor labels are usernames
> rather than the Discord display names a real post would show. Records deleted since creation
> are omitted. The flush runs once a minute in production, so a real post lands up to 60 seconds
> after the times shown here."""

_HOW_PRODUCED = """## How this document was produced

```bash
make db-up && scripts/sync_prod.sh --yes      # sanitized production data
DJANGO_SETTINGS_MODULE=flipfix.settings.dev .venv/bin/python manage.py \\
    replay_notification_coalescing
```

The command reconstructs every event that would have fired a webhook from the `history_type='+'`
rows of `LogEntry`, `ProblemReport`, `PartRequest` and `PartRequestUpdate` (the same basis as
`manage.py analyze_notification_clusters`), resolves each event's actor and machine through the
live `WebhookHandler` API, simulates the debounce with the shipped `COALESCE_QUIET_PERIOD` (5
min) and `COALESCE_MAX_WAIT` (15 min), and renders the real payloads that `build_pending_posts`
produces. Cases are selected by rule rather than hard-coded, so the document survives a re-sync.

The intake checklists carry `announce=False` in the local copy, standing in for the wiki
template's `announce="no"` flag, which is how they are suppressed in production once the
`Intake checklist` page carries it.
"""
