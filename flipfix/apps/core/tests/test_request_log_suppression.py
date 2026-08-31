"""Tests for SuppressRequestLogsMixin's ordering and cleanup guarantees."""

from __future__ import annotations

import logging

from django.test import SimpleTestCase, TestCase, tag

from flipfix.apps.core.test_utils import SuppressRequestLogsMixin


@tag("unit")
class SuppressRequestLogsOrderingTests(SuppressRequestLogsMixin, TestCase):
    """Suppression has to be in place before class fixtures are built.

    Django calls ``setUpTestData`` from ``TestCase.setUpClass``, so a mixin that
    raises the log level only *after* ``super().setUpClass()`` misses every
    request issued while building class fixtures — which is exactly where a
    class that deliberately provokes 404s and 405s does its work.
    """

    level_while_building_fixtures: int | None = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.level_while_building_fixtures = logging.getLogger("django.request").level

    def test_request_logs_are_suppressed_while_fixtures_are_built(self):
        self.assertEqual(self.level_while_building_fixtures, logging.CRITICAL)

    def test_request_logs_are_suppressed_during_the_test_itself(self):
        self.assertEqual(logging.getLogger("django.request").level, logging.CRITICAL)


class _ExplodingSetUp:
    """Stand-in for a TestCase whose setUpClass fails."""

    @classmethod
    def setUpClass(cls):
        raise RuntimeError("class setup failed")


class _Harness(SuppressRequestLogsMixin, _ExplodingSetUp):
    pass


@tag("unit")
class SuppressRequestLogsRestoreTests(SimpleTestCase):
    """A failed class setup must not leave the logger muted for the whole run."""

    def test_level_is_restored_when_class_setup_raises(self):
        logger = logging.getLogger("django.request")
        original = logger.level
        with self.assertRaises(RuntimeError):
            _Harness.setUpClass()
        self.assertEqual(logger.level, original)
