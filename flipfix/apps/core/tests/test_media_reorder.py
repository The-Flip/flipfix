"""Tests for MediaUploadMixin.handle_reorder_media."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, tag

from flipfix.apps.accounts.models import MaintainerMedia
from flipfix.apps.core.mixins import MediaUploadMixin
from flipfix.apps.core.test_utils import MINIMAL_PNG, TemporaryMediaMixin, TestDataMixin


def _make_media(maintainer, count: int) -> list[MaintainerMedia]:
    """Create `count` MaintainerMedia rows attached to `maintainer`."""
    return [
        MaintainerMedia.objects.create(
            maintainer=maintainer,
            media_type=MaintainerMedia.MediaType.PHOTO,
            file=SimpleUploadedFile(f"test-{i}.png", MINIMAL_PNG, content_type="image/png"),
        )
        for i in range(count)
    ]


class _ReorderViewStub(MediaUploadMixin):
    """Minimal stand-in for a real view; exposes the mixin in isolation."""

    def __init__(self, media_model: Any, parent: Any) -> None:
        self._media_model = media_model
        self._parent = parent

    def get_media_model(self) -> Any:
        return self._media_model

    def get_media_parent(self) -> Any:
        return self._parent


@tag("views")
class HandleReorderMediaTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Direct unit tests for the reorder branch of MediaUploadMixin."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.media = _make_media(self.maintainer, 3)
        self.view = _ReorderViewStub(MaintainerMedia, self.maintainer)

    def _post(self, ordered_ids: list) -> Any:
        body = urlencode([("ordered_ids", str(i)) for i in ordered_ids])
        request = self.factory.post(
            "/profile/",
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        return self.view.handle_reorder_media(request)

    def test_reorders_existing_items(self):
        """Submitting a permuted full set updates display_order."""
        new_order = [self.media[2].pk, self.media[0].pk, self.media[1].pk]
        response = self._post(new_order)

        self.assertEqual(response.status_code, 200)
        for index, pk in enumerate(new_order):
            self.assertEqual(MaintainerMedia.objects.get(pk=pk).display_order, index)

    def test_rejects_subset(self):
        """A submission missing one of the parent's items is rejected."""
        partial = [self.media[0].pk, self.media[1].pk]
        response = self._post(partial)

        self.assertEqual(response.status_code, 400)
        # display_order is unchanged from initial values assigned at create time.
        original = [m.display_order for m in self.media]
        refreshed = [MaintainerMedia.objects.get(pk=m.pk).display_order for m in self.media]
        self.assertEqual(original, refreshed)

    def test_rejects_extra_id(self):
        """Including an id not belonging to this parent is rejected."""
        bogus_id = max(m.pk for m in self.media) + 9999
        ids = [m.pk for m in self.media] + [bogus_id]
        response = self._post(ids)

        self.assertEqual(response.status_code, 400)

    def test_rejects_duplicates(self):
        """A submission with duplicate ids is rejected."""
        dup = [self.media[0].pk, self.media[0].pk, self.media[1].pk]
        response = self._post(dup)

        self.assertEqual(response.status_code, 400)

    def test_rejects_non_integer_ids(self):
        """Garbage in ordered_ids returns 400, not 500."""
        body = urlencode([("ordered_ids", "not-an-int")])
        request = self.factory.post(
            "/profile/",
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        response = self.view.handle_reorder_media(request)
        self.assertEqual(response.status_code, 400)

    def test_empty_submission_ok_when_no_media(self):
        """A parent with no media accepts an empty ordered_ids list."""
        MaintainerMedia.objects.filter(maintainer=self.maintainer).delete()
        response = self._post([])
        self.assertEqual(response.status_code, 200)

    def test_other_parent_media_unaffected(self):
        """Reordering one maintainer's media doesn't touch another's."""
        from flipfix.apps.core.test_utils import create_maintainer_user

        other_user = create_maintainer_user(username="other-maintainer")
        from flipfix.apps.accounts.models import Maintainer

        other_maintainer = Maintainer.objects.get(user=other_user)
        other_media = _make_media(other_maintainer, 2)
        other_orders_before = [m.display_order for m in other_media]

        new_order = [self.media[2].pk, self.media[0].pk, self.media[1].pk]
        response = self._post(new_order)
        self.assertEqual(response.status_code, 200)

        other_orders_after = [
            MaintainerMedia.objects.get(pk=m.pk).display_order for m in other_media
        ]
        self.assertEqual(other_orders_before, other_orders_after)


@tag("models")
class MaintainerMediaDisplayOrderTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for the display_order auto-assignment on MaintainerMedia.save()."""

    def test_first_item_gets_zero(self):
        """First MaintainerMedia for a maintainer has display_order=0."""
        media = MaintainerMedia.objects.create(
            maintainer=self.maintainer,
            media_type=MaintainerMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("first.png", MINIMAL_PNG, content_type="image/png"),
        )
        self.assertEqual(media.display_order, 0)

    def test_subsequent_items_increment(self):
        """Each new item gets max(existing)+1."""
        items = _make_media(self.maintainer, 4)
        self.assertEqual([m.display_order for m in items], [0, 1, 2, 3])

    def test_explicit_display_order_is_preserved(self):
        """Callers may still pass an explicit display_order."""
        media = MaintainerMedia.objects.create(
            maintainer=self.maintainer,
            media_type=MaintainerMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("explicit.png", MINIMAL_PNG, content_type="image/png"),
            display_order=99,
        )
        self.assertEqual(media.display_order, 99)

    def test_existing_row_save_does_not_renumber(self):
        """Saving an existing row leaves its display_order untouched."""
        media = _make_media(self.maintainer, 1)[0]
        media.display_order = 42
        media.save()
        self.assertEqual(MaintainerMedia.objects.get(pk=media.pk).display_order, 42)

    def test_per_maintainer_counter(self):
        """display_order numbering is scoped per maintainer."""
        from flipfix.apps.core.test_utils import create_maintainer_user

        other_user = create_maintainer_user(username="other-counter")
        from flipfix.apps.accounts.models import Maintainer

        other = Maintainer.objects.get(user=other_user)
        _make_media(self.maintainer, 3)
        other_items = _make_media(other, 2)
        self.assertEqual([m.display_order for m in other_items], [0, 1])
