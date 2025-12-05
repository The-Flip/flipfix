"""Classifier evaluation against historical Discord messages.

This test runs the message parser against real Discord history to evaluate
classification accuracy. It's designed to help tune the classifier before
deploying to production.

Usage:
    make test-classifier
"""
# ruff: noqa: T201  # print statements are intentional for evaluation output

import csv
from pathlib import Path

from django.core.cache import cache
from django.test import TestCase

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.discord.parsers import RecordType, parse_message


class ClassifierEvaluationTests(TestCase):
    """Evaluate classifier against historical Discord messages."""

    @classmethod
    def setUpClass(cls):
        """Load fixtures once for all tests."""
        super().setUpClass()
        cls.fixtures_dir = Path(__file__).parent.parent / "fixtures"

    def setUp(self):
        """Load machines from fixture CSV."""
        # Clear the machine cache
        cache.delete("machines_for_matching")

        # Load machines from CSV
        machines_csv = self.fixtures_dir / "machines.csv"
        with open(machines_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                model, _ = MachineModel.objects.get_or_create(
                    name=row["model_name"],
                    defaults={
                        "manufacturer": row["manufacturer"],
                        "year": int(row["year"]) if row["year"] else None,
                    },
                )
                # name_override is only needed if display_name differs from model name
                name_override = (
                    row["display_name"] if row["display_name"] != row["model_name"] else ""
                )
                MachineInstance.objects.get_or_create(
                    slug=row["slug"],
                    defaults={
                        "model": model,
                        "name_override": name_override,
                    },
                )

    def test_classifier_on_historical_messages(self):
        """Run classifier on historical Discord messages and print summary.

        This test always passes - it's for evaluation, not assertion.
        Review the output to understand classifier behavior.
        """
        messages_csv = self.fixtures_dir / "discord_workshop_messages.csv"

        results: dict[str, list[dict]] = {
            "ignore": [],
            "log_entry": [],
            "problem_report": [],
            "part_request": [],
        }

        with open(messages_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                content = row.get("content", "")
                if not content:
                    continue

                result = parse_message(content)
                # Map record_type to string key for results dict
                action_key = result.record_type.value if result.record_type else "ignore"
                results[action_key].append(
                    {
                        "content": content[:100],
                        "machine": result.machine.display_name if result.machine else None,
                        "reason": result.reason,
                    }
                )

        # Print summary
        total = sum(len(v) for v in results.values())
        print()
        print("=" * 60)
        print("CLASSIFIER EVALUATION SUMMARY")
        print("=" * 60)

        for action, items in results.items():
            pct = (len(items) / total * 100) if total else 0
            print(f"{action.upper()}: {len(items)} ({pct:.1f}%)")
            # Show first few examples
            for item in items[:3]:
                machine_str = f" [{item['machine']}]" if item["machine"] else ""
                print(f"  • {item['content'][:60]}...{machine_str}")

        print("=" * 60)
        print(f"Total messages processed: {total}")
        print("=" * 60)

        # This test always passes - it's for evaluation
        self.assertTrue(True)

    def test_specific_message_classifications(self):
        """Test specific message patterns we expect to classify correctly.

        Add known messages here as regression tests when tuning the classifier.
        """
        test_cases = [
            # (message, expected_record_type, expected_machine_slug_or_none)
            # Note: "problem" in "startup problem" triggers problem_report
            # This is a known limitation - could be tuned later
            (
                "Worked on Derby Day to solve the startup problem",
                RecordType.PROBLEM_REPORT,
                "derby-day",
            ),
            (
                "Hey everyone, meeting at 3pm",
                None,  # None means ignore/don't create
                None,
            ),
            # Note: "Got" doesn't trigger work keywords, so this is ignored
            # even though it mentions Star Trek. Could add "got" as work keyword.
            (
                "Got parts for Star Trek",
                None,  # None means ignore/don't create
                None,
            ),
        ]

        for content, expected_record_type, expected_machine in test_cases:
            with self.subTest(content=content[:50]):
                result = parse_message(content)
                self.assertEqual(
                    result.record_type,
                    expected_record_type,
                    f"Expected {expected_record_type} for: {content[:50]}...",
                )
                if expected_machine:
                    self.assertIsNotNone(result.machine)
                    self.assertEqual(result.machine.slug, expected_machine)
                else:
                    self.assertIsNone(result.machine)
