"""Tests for the feed source dynamic registry."""

from django.db.models import QuerySet
from django.test import TestCase, tag

from the_flip.apps.core.feed import (
    EntryType,
    FeedEntrySource,
    _feed_source_registry,
    clear_feed_source_registry,
    register_feed_source,
)


def _dummy_queryset() -> QuerySet:
    """Placeholder queryset factory for registration tests."""
    return QuerySet()  # pragma: no cover


@tag("models")
class FeedSourceRegistryStartupTests(TestCase):
    """Tests that apps register their feed sources via AppConfig.ready()."""

    def test_all_expected_sources_registered(self):
        """All four feed sources are present in the registry after startup."""
        expected = {
            EntryType.LOG,
            EntryType.PROBLEM_REPORT,
            EntryType.PART_REQUEST,
            EntryType.PART_REQUEST_UPDATE,
        }
        self.assertEqual(set(_feed_source_registry.keys()), expected)

    def test_registered_values_are_feed_entry_sources(self):
        """Registry stores FeedEntrySource instances."""
        for source in _feed_source_registry.values():
            self.assertIsInstance(source, FeedEntrySource)

    def test_each_source_has_callable_queryset_factory(self):
        """Each registered source has a callable get_base_queryset."""
        for source in _feed_source_registry.values():
            self.assertTrue(
                callable(source.get_base_queryset),
                f"Source '{source.entry_type}' has non-callable get_base_queryset",
            )


@tag("models")
class RegisterFeedSourceTests(TestCase):
    """Tests for the register/clear API itself.

    These tests clear and restore the registry, so they verify the
    registration mechanics independently of AppConfig.ready().
    """

    def setUp(self):
        self._saved = dict(_feed_source_registry)

    def tearDown(self):
        _feed_source_registry.clear()
        _feed_source_registry.update(self._saved)

    def test_register_adds_source(self):
        """register_feed_source() adds a source keyed by entry_type."""
        clear_feed_source_registry()
        source = FeedEntrySource(
            entry_type=EntryType.LOG,
            get_base_queryset=_dummy_queryset,
            machine_filter_field="machine",
            global_select_related=("machine",),
        )
        register_feed_source(source)
        self.assertIs(_feed_source_registry[EntryType.LOG], source)

    def test_duplicate_registration_raises(self):
        """Registering the same entry type twice raises ValueError."""
        clear_feed_source_registry()
        source = FeedEntrySource(
            entry_type=EntryType.LOG,
            get_base_queryset=_dummy_queryset,
            machine_filter_field="machine",
            global_select_related=("machine",),
        )
        register_feed_source(source)
        with self.assertRaises(ValueError) as ctx:
            register_feed_source(source)
        self.assertIn("already registered", str(ctx.exception))

    def test_clear_empties_registry(self):
        """clear_feed_source_registry() removes all entries."""
        clear_feed_source_registry()
        self.assertEqual(len(_feed_source_registry), 0)
