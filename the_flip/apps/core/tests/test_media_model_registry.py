"""Tests for the media model dynamic registry."""

from django.test import TestCase, tag

from the_flip.apps.core.models import (
    _MEDIA_MODEL_REGISTRY,
    AbstractMedia,
    clear_media_model_registry,
    get_media_model,
    register_media_model,
)
from the_flip.apps.maintenance.models import LogEntryMedia, ProblemReportMedia
from the_flip.apps.parts.models import PartRequestMedia, PartRequestUpdateMedia


@tag("models")
class MediaModelRegistryTests(TestCase):
    """Tests that apps register their media models via AppConfig.ready()."""

    def test_all_expected_models_registered(self):
        """All four media models are present in the registry after startup."""
        expected = {
            "LogEntryMedia",
            "ProblemReportMedia",
            "PartRequestMedia",
            "PartRequestUpdateMedia",
        }
        self.assertEqual(set(_MEDIA_MODEL_REGISTRY.keys()), expected)

    def test_registered_values_are_classes(self):
        """Registry stores actual model classes, not import path strings."""
        for model_class in _MEDIA_MODEL_REGISTRY.values():
            self.assertTrue(
                issubclass(model_class, AbstractMedia),
                f"{model_class} is not a subclass of AbstractMedia",
            )

    def test_get_media_model_returns_correct_class(self):
        """get_media_model() returns the right class for each name."""
        self.assertIs(get_media_model("LogEntryMedia"), LogEntryMedia)
        self.assertIs(get_media_model("ProblemReportMedia"), ProblemReportMedia)
        self.assertIs(get_media_model("PartRequestMedia"), PartRequestMedia)
        self.assertIs(get_media_model("PartRequestUpdateMedia"), PartRequestUpdateMedia)

    def test_get_media_model_unknown_name_raises(self):
        """get_media_model() raises ValueError for unregistered names."""
        with self.assertRaises(ValueError) as ctx:
            get_media_model("BogusMedia")
        self.assertIn("Unknown media model", str(ctx.exception))


@tag("models")
class RegisterMediaModelTests(TestCase):
    """Tests for the register/clear API itself.

    These tests clear and restore the registry, so they verify the
    registration mechanics independently of AppConfig.ready().
    """

    def setUp(self):
        self._saved = dict(_MEDIA_MODEL_REGISTRY)

    def tearDown(self):
        _MEDIA_MODEL_REGISTRY.clear()
        _MEDIA_MODEL_REGISTRY.update(self._saved)

    def test_register_adds_model(self):
        """register_media_model() adds a class keyed by __name__."""
        clear_media_model_registry()
        register_media_model(LogEntryMedia)
        self.assertIs(get_media_model("LogEntryMedia"), LogEntryMedia)

    def test_duplicate_registration_raises(self):
        """Registering the same model twice raises ValueError."""
        clear_media_model_registry()
        register_media_model(LogEntryMedia)
        with self.assertRaises(ValueError) as ctx:
            register_media_model(LogEntryMedia)
        self.assertIn("already registered", str(ctx.exception))

    def test_clear_empties_registry(self):
        """clear_media_model_registry() removes all entries."""
        clear_media_model_registry()
        self.assertEqual(len(_MEDIA_MODEL_REGISTRY), 0)
