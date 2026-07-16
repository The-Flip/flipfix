# Daily Maintenance Report

An at-a-glance "emoji board" of every machine's health, grouped by museum area,
posted to Discord each morning and browsable as a web page.

Status: IN PROGRESS. The health model, zone grouping, report builder
([`flipfix/apps/maintenance/reports.py`](../../flipfix/apps/maintenance/reports.py)),
the `daily_maintenance_report` management command, and the maintainer web landing
page (`/logs/daily-report/`) are implemented. The daily Discord post is next.

## Rationale

Maintainers and the owner want a daily pulse: _what's playing, what's down, and
what's actively being worked._ The [wall display](ProblemPriority.md#wall-display)
answers "what should I work on next" from the workshop; this report answers "how
is the collection doing" from the player's chair, and nudges people to keep
momentum on in-progress repairs.

## The health model (player's-eye view)

Each machine collapses to a single **emoji** by worst-wins over its
`operational_status` and its open problem-report priorities:

| Emoji | State       | Trigger                                    |
| ----- | ----------- | ------------------------------------------ |
| 😭    | down        | `broken`, or an open **Unplayable** report |
| 🔧    | being fixed | status `fixing`                            |
| 😟    | major issue | open **Major** report                      |
| 🤔    | untriaged   | open **Untriaged** report                  |
| 🙂    | minor issue | open **Minor** report                      |
| 😐    | unknown     | status `unknown`, nothing else             |
| 😀    | good        | everything else                            |

`operational_status` already reflects the Unplayable→Broken invariant (enforced
at write time by [`status_rules`](../../flipfix/apps/maintenance/status_rules.py)),
so the classifier reads it directly.

**Tasks never change the emoji.** A Task (from
[Problem Priority](ProblemPriority.md)) is a routine chore — "clean the
playfield," "replace the balls" — that doesn't affect whether the machine plays.
So a machine whose only open reports are Tasks reads exactly like one with no
reports. Tasks are invisible to the face (and to the "needs attention" list); the
`--verbose` view still shows them so you can see they exist.

## Zones (front vs back of house)

The two report sections come from a machine's **`Location.zone`**
(`front` / `workshop` / `storage` / `hidden`; see [Datamodel](../Datamodel.md)):

- **Front of House** (`front` — Coin-Op, Museum): machines are _expected to play_.
  Pulse: `N/M playing well · D down · F being fixed`. A down machine here is a fire.
- **Back of House** (`workshop` + `storage`): machines are _expected to be under
  repair_, so "down" is normal. Pulse: `N in the shop · S stalled (>2w) · R ready
to return`. The written list and the stalled count are **workshop-only** —
  storage machines are parked, so they render as 📦 boxes (not health faces) and
  stay out of the queue.
- `hidden` (the default for a new location) and machines with no location are
  excluded from the report.

Each zone's emoji row is ordered by **machine age** (`model.year`, oldest first).

## Freshness

The "needs attention" list shows only real issues (down / fixing / major /
untriaged), **most-recently-touched first** and capped at 5 — the goal is to keep
momentum on active work, not nag about the oldest neglected thing. Each line
carries a state-specific relative time:

- **down** → when it was marked down (from the machine's `simple_history`
  status→broken transition; falls back to the driving Unplayable report's date).
- **untriaged / major** → when the report came in.
- **being fixed** → the last log entry's date.

## Outputs (one builder, three surfaces)

[`reports.build_report()`](../../flipfix/apps/maintenance/reports.py) does all DB
access (~4 queries, no N+1) and returns plain dataclasses. Renderers stay pure so
the surfaces can't drift:

- **`daily_maintenance_report` command** — prints the compact digest, or a
  per-machine `--verbose` breakdown.
- **Daily Discord post** _(planned)_ — the compact **emoji-digest** as webhook
  `content` (fits the 2000-char cap; backtick rows stay monospace), with a link
  to the landing page. Posted by a django-q2 `Schedule` (the first recurring job)
  running on the existing `qcluster` worker. The Discord _bot_ is read-only, so
  posting goes through the webhook (`discord/tasks.py`).
- **Maintainer web landing page** (`/logs/daily-report/`) — the verbose board as
  HTML, where machines link to their detail page, report mentions link to the
  driving report, and durations link to the log entry (a bare history-driven
  "down" date, with no linkable entry, stays plain text).

## Rejected alternatives

- **Post via the Discord bot.** The bot is an interactive gateway client with no
  channel-post path; the worker can't reach it. The outbound webhook is the only
  mechanism.
- **Absolute dates** ("down since 9 Jul"). Relative time ("7w ago") reads the
  staleness at a glance and needs no year disambiguation; the landing page uses
  the same server-rendered strings as Discord for parity.
- **Stalest-first ordering.** Surfacing the oldest-neglected machine first buries
  active work; most-recently-touched-first keeps people going on what's in flight.
- **A boolean per report section + magic "storage" slug.** A single admin-editable
  `Location.zone` enum captures both the section grouping and the storage-parked
  behavior without string-matching a slug.
