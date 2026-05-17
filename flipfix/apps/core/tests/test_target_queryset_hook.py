"""Locks down the ``LinkType.target_queryset`` contract end-to-end.

Independent of any specific app's link type, this test registers a fixture
``LinkType`` with a scoping callable and asserts that all four touchpoints
honor it: save-time conversion, render-time resolution, storage-to-authoring,
and the autocomplete API. Future link types added with ``target_queryset``
get this same contract for free.
"""

import uuid

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import MachineInstance, MachineModel
from flipfix.apps.core.markdown_links import (
    LinkType,
    _patterns,
    _registry,
    convert_authoring_to_storage,
    convert_storage_to_authoring,
    register,
    render_all_links,
    sync_references,
)
from flipfix.apps.core.models import RecordReference
from flipfix.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from flipfix.apps.maintenance.models import LogEntry

# Prefix marks "in scope" for the fixture link type. A separate prefix is used
# so the existing ``machine`` link type's targets stay disjoint from ours.
IN_SCOPE_PREFIX = "scoped-"
FIXTURE_LINK_NAME = "scopedmachine"


def _serialize(obj):
    return {"label": obj.name, "ref": obj.slug}


def _in_scope_machines(model):
    return model.objects.filter(slug__startswith=IN_SCOPE_PREFIX)


def _register_fixture_link_type():
    register(
        LinkType(
            name=FIXTURE_LINK_NAME,
            model_path="catalog.MachineInstance",
            slug_field="slug",
            label="Scoped Machine",
            description="Fixture link type for target_queryset contract tests",
            url_name="maintainer-machine-detail",
            url_kwarg="slug",
            url_field="slug",
            label_field="name",
            target_queryset=_in_scope_machines,
            autocomplete_search_fields=("name", "slug"),
            autocomplete_ordering=("name",),
            autocomplete_serialize=_serialize,
            sort_order=999,
        )
    )


def _unregister_fixture_link_type():
    _registry.pop(FIXTURE_LINK_NAME, None)
    _patterns.pop(FIXTURE_LINK_NAME, None)


@tag("views")
class TargetQuerysetHookTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """End-to-end coverage of the ``target_queryset`` hook."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _register_fixture_link_type()
        # Pair the cleanup with the setup so the unregister can't be lost
        # if a future setUpClass step is added between them and raises.
        cls.addClassCleanup(_unregister_fixture_link_type)

    def setUp(self):
        super().setUp()
        suffix = uuid.uuid4().hex[:8]
        self.model = MachineModel.objects.create(name=f"Model {suffix}", slug=f"model-{suffix}")
        self.in_scope = MachineInstance.objects.create(
            model=self.model,
            name=f"In Scope {suffix}",
            slug=f"{IN_SCOPE_PREFIX}{suffix}",
        )
        self.out_of_scope = MachineInstance.objects.create(
            model=self.model,
            name=f"Out Of Scope {suffix}",
            slug=f"other-{suffix}",
        )

    # ------------------------------------------------------------------
    # In-scope: behaves like a normal link type.
    # ------------------------------------------------------------------

    def test_in_scope_converts_authoring_to_storage(self):
        content = f"See [[{FIXTURE_LINK_NAME}:{self.in_scope.slug}]]."
        result = convert_authoring_to_storage(content)

        self.assertEqual(result, f"See [[{FIXTURE_LINK_NAME}:id:{self.in_scope.pk}]].")

    def test_in_scope_renders_as_link(self):
        result = render_all_links(f"[[{FIXTURE_LINK_NAME}:id:{self.in_scope.pk}]]")

        self.assertIn(self.in_scope.name, result)
        self.assertIn("/machines/", result)

    def test_in_scope_round_trips_through_storage(self):
        result = convert_storage_to_authoring(f"[[{FIXTURE_LINK_NAME}:id:{self.in_scope.pk}]]")

        self.assertEqual(result, f"[[{FIXTURE_LINK_NAME}:{self.in_scope.slug}]]")

    def test_in_scope_appears_in_autocomplete(self):
        self.client.force_login(self.maintainer_user)
        url = reverse("api-link-targets")

        response = self.client.get(url + f"?type={FIXTURE_LINK_NAME}&q={self.in_scope.slug}")

        self.assertEqual(response.status_code, 200)
        refs = [r["ref"] for r in response.json()["results"]]
        self.assertIn(self.in_scope.slug, refs)

    # ------------------------------------------------------------------
    # Out-of-scope: hidden from the link surface at every layer.
    # ------------------------------------------------------------------

    def test_out_of_scope_authoring_raises_validation_error(self):
        content = f"See [[{FIXTURE_LINK_NAME}:{self.out_of_scope.slug}]]."

        with self.assertRaises(ValidationError):
            convert_authoring_to_storage(content)

    def test_out_of_scope_renders_as_broken_link(self):
        result = render_all_links(f"[[{FIXTURE_LINK_NAME}:id:{self.out_of_scope.pk}]]")

        self.assertIn("*[broken link]*", result)

    def test_out_of_scope_storage_to_authoring_leaves_token_unchanged(self):
        token = f"[[{FIXTURE_LINK_NAME}:id:{self.out_of_scope.pk}]]"

        result = convert_storage_to_authoring(token)

        self.assertEqual(result, token)

    def test_out_of_scope_excluded_from_autocomplete(self):
        self.client.force_login(self.maintainer_user)
        url = reverse("api-link-targets")

        response = self.client.get(url + f"?type={FIXTURE_LINK_NAME}&q={self.out_of_scope.slug}")

        self.assertEqual(response.status_code, 200)
        refs = [r["ref"] for r in response.json()["results"]]
        self.assertNotIn(self.out_of_scope.slug, refs)

    # ------------------------------------------------------------------
    # sync_references: prunes rows that fall out of scope.
    # ------------------------------------------------------------------

    def test_sync_references_prunes_out_of_scope_target(self):
        """When a previously in-scope target leaves the scope, an existing
        RecordReference is pruned on the next sync — even though the
        source content still mentions it.
        """
        source = LogEntry.objects.create(machine=self.machine, text="placeholder")
        content = f"See [[{FIXTURE_LINK_NAME}:id:{self.in_scope.pk}]]."

        sync_references(source, content)

        source_ct = ContentType.objects.get_for_model(source)
        target_ct = ContentType.objects.get_for_model(MachineInstance)
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=source_ct,
                source_id=source.pk,
                target_type=target_ct,
                target_id=self.in_scope.pk,
            ).exists()
        )

        # Move the target out of scope by renaming its slug.
        MachineInstance.objects.filter(pk=self.in_scope.pk).update(
            slug=f"out-of-scope-{self.in_scope.pk}"
        )

        sync_references(source, content)

        self.assertFalse(
            RecordReference.objects.filter(
                source_type=source_ct,
                source_id=source.pk,
                target_type=target_ct,
                target_id=self.in_scope.pk,
            ).exists()
        )
