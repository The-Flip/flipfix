"""Tests for the daily-report builder (`build_report`) and zone grouping."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone
from django.utils.text import slugify

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_machine_model,
    create_problem_report,
)
from flipfix.apps.maintenance.models import ProblemReport
from flipfix.apps.maintenance.reports import build_report

S = MachineInstance.OperationalStatus
P = ProblemReport.Priority
Z = Location.Zone


def _loc(name, zone, sort_order=0):
    # Idempotent: migration 0002 seeds Workshop/Storage, so re-zone rather than
    # collide on the unique slug.
    loc, _ = Location.objects.get_or_create(
        slug=slugify(name), defaults={"name": name, "sort_order": sort_order}
    )
    loc.zone = zone
    loc.sort_order = sort_order
    loc.save()
    return loc


def _machine(location, *, status=S.GOOD, year=1990, name=None):
    return create_machine(
        location=location,
        operational_status=status,
        model=create_machine_model(year=year),
        name=name,
    )


@tag("models")
class BuildReportTests(TestCase):
    def setUp(self):
        self.front = _loc("Coin-Op", Z.FRONT, 1)
        self.museum = _loc("Museum", Z.FRONT, 2)
        self.workshop = _loc("Workshop", Z.WORKSHOP, 3)
        self.storage = _loc("Storage", Z.STORAGE, 4)
        self.now = timezone.now()

    def _zone(self, report, key):
        return next(z for z in report.zones if z.key == key)

    def test_two_zones_front_and_back(self):
        report = build_report(self.now)
        self.assertEqual([z.key for z in report.zones], ["front", "back"])

    def test_hidden_zone_machines_excluded(self):
        hidden = _loc("Basement", Z.HIDDEN, 9)
        _machine(hidden)
        _machine(self.front)
        report = build_report(self.now)
        rows = self._zone(report, "front").rows + self._zone(report, "back").rows
        slugs = [row.location_slug for row in rows]
        self.assertNotIn("basement", slugs)

    def test_machine_without_location_excluded(self):
        create_machine(location=None, model=create_machine_model())
        _machine(self.front)
        report = build_report(self.now)
        cells = [c for row in self._zone(report, "front").rows for c in row.cells]
        self.assertEqual(len(cells), 1)

    def test_emoji_row_ordered_by_year_ascending(self):
        _machine(self.front, year=1995, name="Newer")
        _machine(self.front, year=1975, name="Older")
        report = build_report(self.now)
        row = next(r for r in self._zone(report, "front").rows if r.location_slug == "coin-op")
        self.assertEqual([c.name for c in row.cells], ["Older", "Newer"])

    def test_storage_row_flagged_and_excluded_from_queue(self):
        _machine(self.storage, status=S.BROKEN)  # down, but parked
        report = build_report(self.now)
        back = self._zone(report, "back")
        storage_row = next(r for r in back.rows if r.location_slug == "storage")
        self.assertTrue(storage_row.is_storage)
        # storage machine must not appear in the workshop-only attention list
        self.assertEqual(back.attention, [])

    def test_front_pulse_counts(self):
        _machine(self.front, status=S.GOOD)
        _machine(self.front, status=S.BROKEN)
        _machine(self.museum, status=S.FIXING)
        report = build_report(self.now)
        # 1 good (playing), 1 down, 1 fixing → "1/3 playing well · 1 down · 1 being fixed"
        self.assertEqual(
            self._zone(report, "front").pulse, "1/3 playing well · 1 down · 1 being fixed"
        )

    def test_back_pulse_stalled_is_workshop_only(self):
        # workshop broken, last worked 30d ago → stalled; storage broken → not counted
        w = _machine(self.workshop, status=S.BROKEN)
        create_log_entry(machine=w, occurred_at=self.now - timedelta(days=30))
        _machine(self.storage, status=S.BROKEN)
        report = build_report(self.now)
        # 2 in the shop, 1 stalled (workshop), 0 ready
        self.assertEqual(
            self._zone(report, "back").pulse, "2 in the shop · 1 stalled (>2w) · 0 ready to return"
        )

    def test_attention_capped_at_5_most_recent_first(self):
        for i in range(6):
            m = _machine(self.front, status=S.BROKEN, name=f"M{i}")
            create_log_entry(machine=m, occurred_at=self.now - timedelta(days=i + 1))
        att = self._zone(build_report(self.now), "front").attention
        self.assertEqual(len(att), 5)
        # M0 worked 1d ago (most recent) first; M5 (6d ago) dropped
        self.assertEqual([m.name for m in att], ["M0", "M1", "M2", "M3", "M4"])

    def test_marked_down_from_history(self):
        m = _machine(self.workshop, status=S.GOOD)
        m.operational_status = S.BROKEN
        m.save()  # simple_history records the change
        health = self._find(build_report(self.now), m.id)
        self.assertEqual(health.health, "down")
        self.assertIsNotNone(health.marked_down_at)

    def test_marked_down_falls_back_to_report_when_no_history(self):
        m = _machine(self.workshop, status=S.BROKEN)
        m.history.all().delete()
        reported = self.now - timedelta(days=20)
        create_problem_report(
            machine=m, priority=P.UNPLAYABLE, status=ProblemReport.Status.OPEN, occurred_at=reported
        )
        health = self._find(build_report(self.now), m.id)
        self.assertEqual(health.marked_down_at, reported)

    def test_driving_report_id_for_down_with_unplayable(self):
        m = _machine(self.workshop, status=S.BROKEN)
        pr = create_problem_report(
            machine=m, priority=P.UNPLAYABLE, status=ProblemReport.Status.OPEN
        )
        health = self._find(build_report(self.now), m.id)
        self.assertEqual(health.driving_report_id, pr.id)

    def test_driving_report_id_none_for_status_only_fixing(self):
        m = _machine(self.workshop, status=S.FIXING)
        health = self._find(build_report(self.now), m.id)
        self.assertEqual(health.health, "fixing")
        self.assertIsNone(health.driving_report_id)

    def test_query_count_is_bounded(self):
        # a down machine forces the history query; count must not scale with machines
        for _ in range(4):
            _machine(self.front, status=S.BROKEN)
        with self.assertNumQueries(4):
            build_report(self.now)

    def _find(self, report, machine_id):
        for z in report.zones:
            for row in z.rows:
                for cell in row.cells:
                    if cell.machine_id == machine_id:
                        return cell
        raise AssertionError(f"machine {machine_id} not in report")
