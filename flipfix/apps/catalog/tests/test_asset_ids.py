"""Tests for asset ID generation and assignment."""

from django.db import IntegrityError
from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.asset_ids import generate_asset_id
from flipfix.apps.core.test_utils import create_machine, create_machine_model


@tag("models")
class GenerateAssetIdTests(TestCase):
    """Tests for the generate_asset_id utility."""

    def test_first_id_is_0001(self):
        """First generated ID should be prefix + 0001."""
        result = generate_asset_id("M", MachineInstance)
        self.assertEqual(result, "M0001")

    def test_increments_from_existing(self):
        """Should increment from the highest existing ID."""
        model = create_machine_model()
        create_machine(model=model, name="Machine 1")  # Gets M0001
        result = generate_asset_id("M", MachineInstance)
        self.assertEqual(result, "M0002")

    def test_handles_gaps(self):
        """Should use max + 1, not count + 1 (handles gaps)."""
        model = create_machine_model()
        m1 = create_machine(model=model, name="Machine 1")  # M0001
        create_machine(model=model, name="Machine 2")  # M0002
        # Delete first machine, creating a gap
        m1.delete()
        result = generate_asset_id("M", MachineInstance)
        self.assertEqual(result, "M0003")

    def test_different_prefix(self):
        """Should work with different prefixes independently."""
        # Create a machine with M prefix
        create_machine()  # M0001
        # Generate with P prefix should start at P0001
        result = generate_asset_id("P", MachineInstance)
        self.assertEqual(result, "P0001")

    def test_custom_pad_width(self):
        """Should respect custom pad width."""
        result = generate_asset_id("X", MachineInstance, pad_width=6)
        self.assertEqual(result, "X000001")


@tag("models")
class MachineInstanceAssetIdTests(TestCase):
    """Tests for asset_id auto-assignment on MachineInstance."""

    def setUp(self):
        self.model = create_machine_model()

    def test_auto_assigned_on_create(self):
        """New machines should get an auto-generated asset_id."""
        machine = MachineInstance.objects.create(model=self.model, name="Auto ID Machine")
        self.assertEqual(machine.asset_id, "M0001")

    def test_sequential_ids(self):
        """Multiple machines should get sequential IDs."""
        m1 = MachineInstance.objects.create(model=self.model, name="Machine 1")
        m2 = MachineInstance.objects.create(model=self.model, name="Machine 2")
        m3 = MachineInstance.objects.create(model=self.model, name="Machine 3")
        self.assertEqual(m1.asset_id, "M0001")
        self.assertEqual(m2.asset_id, "M0002")
        self.assertEqual(m3.asset_id, "M0003")

    def test_preserved_on_update(self):
        """Existing asset_id should not change on save."""
        machine = MachineInstance.objects.create(model=self.model, name="Stable ID Machine")
        original_id = machine.asset_id
        machine.name = "Updated Name"
        machine.save()
        machine.refresh_from_db()
        self.assertEqual(machine.asset_id, original_id)

    def test_uniqueness_enforced(self):
        """Database should enforce unique constraint on asset_id."""
        MachineInstance.objects.create(model=self.model, name="Machine A")
        with self.assertRaises(IntegrityError):
            # Force a duplicate by bypassing save() auto-generation
            MachineInstance.objects.create(model=self.model, name="Machine B", asset_id="M0001")

    def test_create_machine_factory_gets_asset_id(self):
        """The create_machine test factory should also get asset IDs."""
        machine = create_machine(model=self.model)
        self.assertTrue(machine.asset_id.startswith("M"))
        self.assertEqual(len(machine.asset_id), 5)  # M + 4 digits
