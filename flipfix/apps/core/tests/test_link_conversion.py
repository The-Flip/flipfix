"""Tests for [[type:ref]] link conversion and reference syncing (non-page types)."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineInstance, MachineModel
from flipfix.apps.core.markdown_links import (
    convert_authoring_to_storage,
    convert_storage_to_authoring,
    sync_references,
)
from flipfix.apps.core.models import RecordReference
from flipfix.apps.maintenance.models import LogEntry


@tag("views")
class AuthoringToStorageConversionTests(TestCase):
    """Tests for converting authoring format to storage format (machine/model types)."""

    def test_machine_link_converts_to_id(self):
        """[[machine:slug]] converts to [[machine:id:N]]."""
        model = MachineModel.objects.create(name="Black Knight", slug="black-knight")
        machine = MachineInstance.objects.create(model=model, slug="blackout", name="Blackout")

        content = "See [[machine:blackout]] for details."
        result = convert_authoring_to_storage(content)

        self.assertEqual(result, f"See [[machine:id:{machine.pk}]] for details.")

    def test_model_link_converts_to_id(self):
        """[[model:slug]] converts to [[model:id:N]]."""
        model = MachineModel.objects.create(name="Black Knight", slug="black-knight")

        content = "See [[model:black-knight]] for details."
        result = convert_authoring_to_storage(content)

        self.assertEqual(result, f"See [[model:id:{model.pk}]] for details.")

    def test_broken_machine_link_raises_error(self):
        """[[machine:nonexistent]] raises ValidationError."""
        content = "See [[machine:nonexistent]]."

        with self.assertRaises(ValidationError) as ctx:
            convert_authoring_to_storage(content)

        self.assertIn("Machine not found", str(ctx.exception))

    def test_broken_model_link_raises_error(self):
        """[[model:nonexistent]] raises ValidationError."""
        content = "See [[model:nonexistent]]."

        with self.assertRaises(ValidationError) as ctx:
            convert_authoring_to_storage(content)

        self.assertIn("Model not found", str(ctx.exception))

    def test_storage_format_unchanged(self):
        """Links already in storage format are not modified."""
        content = "See [[machine:id:456]] and [[model:id:789]]."
        result = convert_authoring_to_storage(content)

        self.assertEqual(result, content)

    def test_empty_content_unchanged(self):
        """Empty content returns empty."""
        self.assertEqual(convert_authoring_to_storage(""), "")
        self.assertEqual(convert_authoring_to_storage(None), None)


@tag("views")
class StorageToAuthoringConversionTests(TestCase):
    """Tests for converting storage format to authoring format (machine/model types)."""

    def test_machine_link_converts_to_slug(self):
        """[[machine:id:N]] converts to [[machine:slug]]."""
        model = MachineModel.objects.create(name="Model", slug="model")
        machine = MachineInstance.objects.create(model=model, slug="blackout", name="Blackout")

        content = f"See [[machine:id:{machine.pk}]]."
        result = convert_storage_to_authoring(content)

        self.assertEqual(result, "See [[machine:blackout]].")

    def test_model_link_converts_to_slug(self):
        """[[model:id:N]] converts to [[model:slug]]."""
        model = MachineModel.objects.create(name="Black Knight", slug="black-knight")

        content = f"See [[model:id:{model.pk}]]."
        result = convert_storage_to_authoring(content)

        self.assertEqual(result, "See [[model:black-knight]].")

    def test_broken_link_preserved(self):
        """Links to deleted targets remain in storage format."""
        content = "See [[machine:id:88888]] and [[model:id:77777]]."
        result = convert_storage_to_authoring(content)

        self.assertEqual(result, content)


@tag("views")
class ReferenceSyncTests(TestCase):
    """Tests for sync_references function using LogEntry as source."""

    @classmethod
    def setUpTestData(cls):
        model = MachineModel.objects.create(name="Test Model", slug="test-model")
        cls.machine = MachineInstance.objects.create(
            model=model, slug="test-machine", name="Test Machine"
        )

    def _ref_exists(self, source, target):
        """Check whether a RecordReference exists from source to target."""
        source_ct = ContentType.objects.get_for_model(source)
        target_ct = ContentType.objects.get_for_model(target)
        return RecordReference.objects.filter(
            source_type=source_ct,
            source_id=source.pk,
            target_type=target_ct,
            target_id=target.pk,
        ).exists()

    def _ref_count(self, source, target_model=None, target=None):
        """Count RecordReferences from source, optionally filtered by target."""
        source_ct = ContentType.objects.get_for_model(source)
        qs = RecordReference.objects.filter(source_type=source_ct, source_id=source.pk)
        if target is not None:
            target_ct = ContentType.objects.get_for_model(target)
            qs = qs.filter(target_type=target_ct, target_id=target.pk)
        elif target_model is not None:
            target_ct = ContentType.objects.get_for_model(target_model)
            qs = qs.filter(target_type=target_ct)
        return qs.count()

    def test_machine_reference_created(self):
        """Machine links create RecordReference records."""
        entry = LogEntry.objects.create(machine=self.machine, text="test")
        model = MachineModel.objects.create(name="Other", slug="other")
        target = MachineInstance.objects.create(model=model, slug="target", name="Target")

        content = f"See [[machine:id:{target.pk}]]."
        sync_references(entry, content)

        self.assertTrue(self._ref_exists(entry, target))

    def test_model_reference_created(self):
        """Model links create RecordReference records."""
        entry = LogEntry.objects.create(machine=self.machine, text="test")
        target = MachineModel.objects.create(name="Target Model", slug="target-model")

        content = f"See [[model:id:{target.pk}]]."
        sync_references(entry, content)

        self.assertTrue(self._ref_exists(entry, target))

    def test_removed_link_deletes_reference(self):
        """Removing a link from content deletes the reference."""
        entry = LogEntry.objects.create(machine=self.machine, text="test")
        model = MachineModel.objects.create(name="Other", slug="other")
        target = MachineInstance.objects.create(model=model, slug="target", name="Target")

        # First, create a reference
        sync_references(entry, f"See [[machine:id:{target.pk}]].")
        self.assertTrue(self._ref_exists(entry, target))

        # Now remove the link
        sync_references(entry, "No more links.")
        self.assertFalse(self._ref_exists(entry, target))

    def test_duplicate_links_single_reference(self):
        """Multiple links to same target create only one reference."""
        entry = LogEntry.objects.create(machine=self.machine, text="test")
        model = MachineModel.objects.create(name="Other", slug="other")
        target = MachineInstance.objects.create(model=model, slug="target", name="Target")

        content = f"See [[machine:id:{target.pk}]] and also [[machine:id:{target.pk}]]."
        sync_references(entry, content)

        self.assertEqual(self._ref_count(entry, target=target), 1)

    def test_broken_link_no_reference(self):
        """Links to nonexistent targets don't create references."""
        entry = LogEntry.objects.create(machine=self.machine, text="test")

        sync_references(entry, "See [[machine:id:99999]].")

        self.assertEqual(self._ref_count(entry, target_model=MachineInstance), 0)

    def test_orphan_reference_pruned_when_target_hard_deleted(self):
        """Re-syncing a source prunes orphan rows whose target was hard-deleted.

        ``GenericForeignKey`` doesn't cascade on target deletion, so a target
        hard-delete leaves the ``RecordReference`` row dangling. On the next
        sync of any source that still mentions that ID, the orphan row is
        cleaned up — keeping the "what links here" index in sync with what
        the renderer treats as live.
        """
        entry = LogEntry.objects.create(machine=self.machine, text="test")
        model = MachineModel.objects.create(name="Doomed", slug="doomed")
        target = MachineInstance.objects.create(model=model, slug="doomed", name="Doomed")
        content = f"See [[machine:id:{target.pk}]]."

        # Set up the orphan: create the ref row, then hard-delete the target.
        # No cleanup runs because ``register_reference_cleanup()`` only wires
        # post_delete for *source* models, and ``GenericForeignKey`` doesn't
        # cascade — so the ref row survives the target delete, reproducing
        # the exact "orphan in the wild" state.
        sync_references(entry, content)
        self.assertTrue(self._ref_exists(entry, target))

        target_pk = target.pk
        MachineInstance.objects.filter(pk=target_pk).delete()
        orphan_qs = RecordReference.objects.filter(
            source_type=ContentType.objects.get_for_model(entry),
            source_id=entry.pk,
            target_type=ContentType.objects.get_for_model(MachineInstance),
            target_id=target_pk,
        )
        self.assertTrue(
            orphan_qs.exists(), "precondition: orphan row should remain after target hard-delete"
        )

        # Re-syncing the same content prunes the orphan.
        sync_references(entry, content)
        self.assertFalse(orphan_qs.exists())
