"""Tests for the automatic log entry vocabulary in maintenance/auto_log.py.

The builders and the classifier have to stay in step: anything the app writes on
a person's behalf must be recognisable as such afterwards, and anything a person
typed must not be mistaken for it.
"""

from django.test import TestCase, tag

from flipfix.apps.maintenance import auto_log
from flipfix.apps.maintenance.auto_log import AutoLogKind


@tag("models")
class AutoLogClassifyTests(TestCase):
    def test_every_builder_round_trips(self):
        cases = [
            (auto_log.machine_added_text("Gorgar"), AutoLogKind.MACHINE_ADDED, "Gorgar"),
            (auto_log.status_changed_text("Unknown", "Good"), AutoLogKind.STATUS_CHANGED, "Good"),
            (
                auto_log.location_changed_text("No Location", "Storage"),
                AutoLogKind.LOCATION_CHANGED,
                "Storage",
            ),
            (auto_log.moved_to_floor_text("Comet"), AutoLogKind.MOVED_TO_FLOOR, ""),
            (auto_log.CLOSED_REPORT_TEXT, AutoLogKind.REPORT_CLOSED, ""),
            (auto_log.REOPENED_REPORT_TEXT, AutoLogKind.REPORT_REOPENED, ""),
        ]
        for text, expected_kind, expected_detail in cases:
            with self.subTest(text=text):
                recognised = auto_log.classify(text)
                self.assertIsNotNone(recognised, f"{text!r} should be recognised")
                assert recognised is not None  # for the type checker
                self.assertEqual(recognised.kind, expected_kind)
                self.assertEqual(recognised.detail, expected_detail)

    def test_hand_written_entries_are_not_classified(self):
        for text in (
            "Replaced all elastics and cleaned playfield.",
            "",
            "Status of the game is fine",
            "Location of the coin door key is behind the desk",
            "Closed problem report because the part finally arrived",
        ):
            with self.subTest(text=text):
                self.assertIsNone(auto_log.classify(text))

    def test_surrounding_whitespace_is_tolerated(self):
        recognised = auto_log.classify(f"  {auto_log.CLOSED_REPORT_TEXT}\n")
        assert recognised is not None
        self.assertEqual(recognised.kind, AutoLogKind.REPORT_CLOSED)

    def test_action_labels_read_as_headings(self):
        labels = {
            auto_log.machine_added_text("Gorgar"): "Added",
            auto_log.status_changed_text("Unknown", "Good"): "Marked Good",
            auto_log.location_changed_text("Floor", "Storage"): "Moved to Storage",
            auto_log.moved_to_floor_text("Comet"): "Moved to the floor",
            auto_log.CLOSED_REPORT_TEXT: "Closed a problem report",
        }
        for text, expected in labels.items():
            with self.subTest(text=text):
                recognised = auto_log.classify(text)
                assert recognised is not None
                self.assertEqual(recognised.action_label, expected)
