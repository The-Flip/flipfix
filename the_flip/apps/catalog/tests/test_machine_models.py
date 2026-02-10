"""Tests for machine models."""

from django.test import TestCase, tag

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.core.test_utils import create_machine, create_machine_model


@tag("models")
class MachineModelTests(TestCase):
    """Tests for the MachineModel model."""

    def test_slug_generation_on_create(self):
        """Should generate a slug from the name when a new model is created."""
        model = MachineModel.objects.create(name="Test Machine")
        self.assertEqual(model.slug, "test-machine")

    def test_slug_uniqueness(self):
        """Should ensure that generated slugs are unique."""
        # Create two models with names that slugify to the same value
        model1 = MachineModel.objects.create(name="My Machine")
        model2 = MachineModel.objects.create(name="My Machine--")
        self.assertEqual(model1.slug, "my-machine")
        self.assertNotEqual(model1.slug, model2.slug)
        self.assertEqual(model2.slug, "my-machine-2")


@tag("models")
class MachineInstanceModelTests(TestCase):
    """Tests for the MachineInstance model."""

    def setUp(self):
        """Set up a model for instance tests."""
        self.model = create_machine_model(name="Test Model")

    # name field tests

    def test_name_required(self):
        """name field should be required."""
        from django.core.exceptions import ValidationError

        instance = MachineInstance(model=self.model, name="")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_whitespace_only_raises_validation_error(self):
        """Whitespace-only name should raise ValidationError.

        Bug: clean() strips name but doesn't check if result is empty.
        Submitting "   " becomes "" after stripping but passes validation.
        """
        from django.core.exceptions import ValidationError

        instance = MachineInstance(model=self.model, name="   ")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_collision_with_different_model_raises_validation_error(self):
        """Name collision across different models should raise ValidationError.

        Instance names must be unique globally, not just per-model.
        """
        from django.core.exceptions import ValidationError

        # Create existing machine with name "Godzilla"
        existing_model = MachineModel.objects.create(name="Existing Model")
        MachineInstance.objects.create(model=existing_model, name="Godzilla")

        # Try to create new instance with same name (but different model)
        new_model = MachineModel.objects.create(name="Godzilla")
        instance = MachineInstance(model=new_model, name="Godzilla")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_duplicate_raises_validation_error(self):
        """Duplicate name should raise ValidationError from clean()."""
        from django.core.exceptions import ValidationError

        MachineInstance.objects.create(model=self.model, name="Duplicate Name")
        duplicate = MachineInstance(model=self.model, name="Duplicate Name")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("name", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["name"],
            ["A machine with this name already exists."],
        )

    def test_name_duplicate_case_insensitive(self):
        """Name uniqueness should be case-insensitive.

        "Godzilla" and "godzilla" should be treated as the same name.
        """
        from django.core.exceptions import ValidationError

        MachineInstance.objects.create(model=self.model, name="Godzilla")
        duplicate = MachineInstance(model=self.model, name="godzilla")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_stripped_on_clean(self):
        """name should be stripped of leading/trailing whitespace."""
        instance = MachineInstance(model=self.model, name="  Padded Name  ")
        instance.full_clean()

        self.assertEqual(instance.name, "Padded Name")

    # short_name tests

    def test_short_display_name_returns_short_name_if_set(self):
        """short_display_name should return short_name if set."""
        instance = MachineInstance.objects.create(
            model=self.model, name="Test Machine", short_name="Short"
        )
        self.assertEqual(instance.short_display_name, "Short")

    def test_short_display_name_returns_name_if_no_short_name(self):
        """short_display_name should return name if short_name is not set."""
        instance = MachineInstance.objects.create(model=self.model, name="Test Machine")
        self.assertEqual(instance.short_display_name, instance.name)

    def test_short_name_duplicate_raises_validation_error(self):
        """Duplicate short_name should raise ValidationError from clean()."""
        from django.core.exceptions import ValidationError

        create_machine(model=self.model, name="Machine 1", short_name="Duplicate")
        duplicate = MachineInstance(model=self.model, name="Machine 2", short_name="Duplicate")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("short_name", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["short_name"],
            ["A machine with this short name already exists."],
        )

    def test_short_name_empty_string_converted_to_null(self):
        """Empty string short_name should be converted to NULL on save."""
        instance = create_machine(model=self.model, short_name="")

        instance.refresh_from_db()
        self.assertIsNone(instance.short_name)

    def test_short_name_whitespace_only_converted_to_null_via_clean(self):
        """Whitespace-only short_name should be converted to NULL via clean()."""
        instance = MachineInstance(model=self.model, name="Test Machine", short_name="   ")
        instance.full_clean()

        self.assertIsNone(instance.short_name)

    def test_short_name_whitespace_only_converted_to_null_via_save(self):
        """Whitespace-only short_name should be converted to NULL on save (without clean)."""
        instance = create_machine(model=self.model, short_name="   ")

        instance.refresh_from_db()
        self.assertIsNone(instance.short_name)

    def test_short_name_null_allows_multiple_machines(self):
        """Multiple machines with NULL short_name should be allowed."""
        instance1 = create_machine(model=self.model, name="Machine 1", short_name=None)
        instance2 = create_machine(model=self.model, name="Machine 2", short_name=None)
        instance3 = create_machine(model=self.model, name="Machine 3", short_name="")

        self.assertEqual(MachineInstance.objects.count(), 3)
        self.assertIsNone(instance1.short_name)
        self.assertIsNone(instance2.short_name)
        instance3.refresh_from_db()
        self.assertIsNone(instance3.short_name)

    def test_short_name_stripped_on_clean(self):
        """short_name should be stripped of leading/trailing whitespace."""
        instance = MachineInstance(model=self.model, name="Test Machine", short_name="  Padded  ")
        instance.full_clean()

        self.assertEqual(instance.short_name, "Padded")

    def test_slug_generation_on_create(self):
        """Should generate a slug from the name."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance = MachineInstance.objects.create(model=self.model, name="Slug Test Machine")
        self.assertEqual(instance.slug, "slug-test-machine")

    def test_slug_generation_with_custom_name(self):
        """Should use the name for the slug."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance = MachineInstance.objects.create(model=self.model, name="My Custom Game")
        self.assertEqual(instance.slug, "my-custom-game")

    def test_slug_uniqueness(self):
        """Should ensure slugs are unique for machine instances."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance1 = MachineInstance.objects.create(model=self.model, name="Same Name")
        instance2 = MachineInstance.objects.create(model=self.model, name="Same Name #2")
        self.assertNotEqual(instance1.slug, instance2.slug)
        self.assertEqual(instance1.slug, "same-name")
        self.assertEqual(instance2.slug, "same-name-2")
