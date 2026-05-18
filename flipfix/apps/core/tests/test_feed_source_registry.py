"""Tests for the feed source dynamic registry."""

from django.db.models import QuerySet
from django.test import TestCase, tag

from flipfix.apps.core.feed import (
    FeedConfig,
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
            "log",
            "problem_report",
            "part_request",
            "part_request_update",
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

    def test_each_source_has_template_paths(self):
        """Each registered source has machine and global template paths."""
        for source in _feed_source_registry.values():
            self.assertTrue(
                source.machine_template,
                f"Source '{source.entry_type}' has no machine_template",
            )
            self.assertTrue(
                source.global_template,
                f"Source '{source.entry_type}' has no global_template",
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
            entry_type="log",
            get_base_queryset=_dummy_queryset,
            machine_filter_field="machine",
            global_select_related=("machine",),
            machine_template="test/machine.html",
            global_template="test/global.html",
        )
        register_feed_source(source)
        self.assertIs(_feed_source_registry["log"], source)

    def test_duplicate_registration_raises(self):
        """Registering the same entry type twice raises ValueError."""
        clear_feed_source_registry()
        source = FeedEntrySource(
            entry_type="log",
            get_base_queryset=_dummy_queryset,
            machine_filter_field="machine",
            global_select_related=("machine",),
            machine_template="test/machine.html",
            global_template="test/global.html",
        )
        register_feed_source(source)
        with self.assertRaises(ValueError) as ctx:
            register_feed_source(source)
        self.assertIn("already registered", str(ctx.exception))

    def test_clear_empties_registry(self):
        """clear_feed_source_registry() removes all entries."""
        clear_feed_source_registry()
        self.assertEqual(len(_feed_source_registry), 0)


@tag("models")
class FeedConfigInvariantTests(TestCase):
    """Tests for the ``FeedConfig.__post_init__`` source_order_by invariant.

    Multi-source feeds must use the default ``("-occurred_at",)`` order so the
    per-source DB slab aligns with the in-memory merge comparator.  See the
    dataclass docstring for the failure mode this guard prevents.
    """

    _valid_kwargs = {
        "title_suffix": "",
        "breadcrumb_label": None,
        "empty_message": "",
        "search_empty_message": "",
    }

    def test_single_source_can_use_custom_order(self):
        """Single-source configs may override source_order_by freely."""
        config = FeedConfig(
            entry_types=("problem_report",),
            source_order_by=("status_sort", "priority_sort", "-occurred_at"),
            **self._valid_kwargs,
        )
        self.assertEqual(
            config.source_order_by,
            ("status_sort", "priority_sort", "-occurred_at"),
        )

    def test_multi_source_with_custom_order_raises(self):
        """Multi-source config with non-default order is rejected at construction."""
        with self.assertRaises(ValueError) as ctx:
            FeedConfig(
                entry_types=("log", "problem_report"),
                source_order_by=("status_sort",),
                **self._valid_kwargs,
            )
        self.assertIn("source_order_by", str(ctx.exception))

    def test_empty_entry_types_with_custom_order_raises(self):
        """The () sentinel (all registered types) counts as multi-source."""
        with self.assertRaises(ValueError):
            FeedConfig(
                entry_types=(),
                source_order_by=("status_sort",),
                **self._valid_kwargs,
            )

    def test_default_order_allowed_for_any_arity(self):
        """The default order is always valid, regardless of entry_types count."""
        # Single
        FeedConfig(entry_types=("log",), **self._valid_kwargs)
        # Multi
        FeedConfig(entry_types=("log", "problem_report"), **self._valid_kwargs)
        # All
        FeedConfig(entry_types=(), **self._valid_kwargs)

    def test_empty_source_order_by_raises(self):
        """Empty source_order_by is rejected — it would clear DB ordering."""
        with self.assertRaises(ValueError) as ctx:
            FeedConfig(
                entry_types=("log",),
                source_order_by=(),
                **self._valid_kwargs,
            )
        self.assertIn("cannot be empty", str(ctx.exception))
