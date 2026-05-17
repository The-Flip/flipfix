"""Tests for the ``/profile`` photo management section.

Covers:
- Visibility: photo section + bio form only render for directory members.
- Two-form save: bio + account fields persist atomically.
- AJAX upload through ``ProfileUpdateView.post(action=upload_media)``.
- 10-item cap enforced server-side.
- Reorder action persists ``display_order``.
- Delete action removes media + file.
- Non-maintainer authenticated users still see the page (without the
  bio/photo section) and can save account fields.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.accounts.models import MaintainerMedia
from flipfix.apps.accounts.views import MAX_PROFILE_MEDIA
from flipfix.apps.core.test_utils import (
    MINIMAL_PNG,
    TemporaryMediaMixin,
    create_maintainer_user,
    create_user,
)

PROFILE_URL = reverse("profile")


def _make_media(maintainer, **overrides) -> MaintainerMedia:
    return MaintainerMedia.objects.create(
        maintainer=maintainer,
        media_type=MaintainerMedia.MediaType.PHOTO,
        file=SimpleUploadedFile("p.png", MINIMAL_PNG, content_type="image/png"),
        **overrides,
    )


@tag("views")
class ProfileVisibilityTests(TestCase):
    """The photo management section gates on directory membership."""

    def test_directory_member_sees_photo_section(self):
        user = create_maintainer_user(username="alice")
        self.client.force_login(user)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-media-card")
        self.assertContains(response, "data-media-reorder")
        self.assertContains(response, "View public profile")

    def test_shared_account_does_not_see_photo_section(self):
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        self.client.force_login(user)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-media-card")
        self.assertNotContains(response, "View public profile")

    def test_non_maintainer_still_loads_without_photo_section(self):
        """``/profile`` is gated to ``authenticated``, not ``maintainer``."""
        user = create_user(username="orphan")
        self.client.force_login(user)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-media-card")
        # Bio field is also absent — no Maintainer means no maintainer_form.
        self.assertNotContains(response, 'name="bio"')


@tag("views")
class ProfileBioSaveTests(TestCase):
    """Two-form atomic save: account fields + bio together."""

    def setUp(self):
        self.user = create_maintainer_user(username="alice", first_name="Alice")
        self.client.force_login(self.user)

    def test_save_persists_bio_and_account_fields(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "first_name": "Updated",
                "last_name": "",
                "email": "alice@example.com",
                "bio": "Hello *world*",
            },
            follow=True,
        )
        self.assertRedirects(response, PROFILE_URL)
        self.user.refresh_from_db()
        self.user.maintainer.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.maintainer.bio, "Hello *world*")

    def test_blank_bio_allowed(self):
        self.user.maintainer.bio = "old"
        self.user.maintainer.save()
        self.client.post(
            PROFILE_URL,
            {
                "first_name": "Alice",
                "last_name": "",
                "email": "alice@example.com",
                "bio": "",
            },
        )
        self.user.maintainer.refresh_from_db()
        self.assertEqual(self.user.maintainer.bio, "")

    def test_invalid_email_rolls_back_bio(self):
        """Atomic save: an invalid email must not persist a bio change."""
        other = create_maintainer_user(username="taken")
        response = self.client.post(
            PROFILE_URL,
            {
                "first_name": "Alice",
                "last_name": "",
                "email": other.email,  # already taken
                "bio": "should not persist",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.maintainer.refresh_from_db()
        self.assertEqual(self.user.maintainer.bio, "")


@tag("views")
class ProfileMediaUploadTests(TemporaryMediaMixin, TestCase):
    """``action=upload_media`` AJAX flow on ``/profile``."""

    def setUp(self):
        super().setUp()
        self.user = create_maintainer_user(username="alice")
        self.client.force_login(self.user)

    def _upload(self):
        upload = SimpleUploadedFile("p.png", MINIMAL_PNG, content_type="image/png")
        return self.client.post(
            PROFILE_URL,
            {"action": "upload_media", "media_file": upload},
        )

    def test_upload_creates_media(self):
        response = self._upload()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(MaintainerMedia.objects.filter(maintainer=self.user.maintainer).count(), 1)

    def test_max_cap_blocks_eleventh_upload(self):
        for _ in range(MAX_PROFILE_MEDIA):
            _make_media(self.user.maintainer)
        response = self._upload()
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("Maximum", body["error"])
        self.assertEqual(
            MaintainerMedia.objects.filter(maintainer=self.user.maintainer).count(),
            MAX_PROFILE_MEDIA,
        )

    def test_upload_forbidden_for_non_maintainer(self):
        user = create_user(username="orphan")
        self.client.force_login(user)
        response = self._upload()
        self.assertEqual(response.status_code, 403)

    def test_upload_forbidden_for_shared_account(self):
        """Shared terminal accounts have a Maintainer but aren't in the
        directory — the AJAX endpoint must match the template visibility
        gate, not just the Maintainer-exists check."""
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        self.client.force_login(user)
        response = self._upload()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MaintainerMedia.objects.filter(maintainer=user.maintainer).count(), 0)


@tag("views")
class ProfileMediaDeleteTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = create_maintainer_user(username="alice")
        self.client.force_login(self.user)

    def test_delete_removes_media(self):
        media = _make_media(self.user.maintainer)
        response = self.client.post(
            PROFILE_URL,
            {"action": "delete_media", "media_id": media.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(MaintainerMedia.objects.filter(pk=media.pk).exists())

    def test_cannot_delete_other_users_media(self):
        other = create_maintainer_user(username="bob")
        media = _make_media(other.maintainer)
        response = self.client.post(
            PROFILE_URL,
            {"action": "delete_media", "media_id": media.id},
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MaintainerMedia.objects.filter(pk=media.pk).exists())


@tag("views")
class ProfileMediaReorderTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = create_maintainer_user(username="alice")
        self.client.force_login(self.user)
        self.m1 = _make_media(self.user.maintainer)
        self.m2 = _make_media(self.user.maintainer)
        self.m3 = _make_media(self.user.maintainer)

    def test_reorder_persists_display_order(self):
        response = self.client.post(
            PROFILE_URL,
            {"action": "reorder_media", "ordered_ids": [self.m3.id, self.m1.id, self.m2.id]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.m1.refresh_from_db()
        self.m2.refresh_from_db()
        self.m3.refresh_from_db()
        self.assertEqual(self.m3.display_order, 0)
        self.assertEqual(self.m1.display_order, 1)
        self.assertEqual(self.m2.display_order, 2)

    def test_reorder_rejects_mismatched_set(self):
        response = self.client.post(
            PROFILE_URL,
            {"action": "reorder_media", "ordered_ids": [self.m1.id, self.m2.id]},
        )
        self.assertEqual(response.status_code, 400)

    def test_reorder_cannot_include_other_users_media(self):
        other = create_maintainer_user(username="bob")
        other_media = _make_media(other.maintainer)
        response = self.client.post(
            PROFILE_URL,
            {
                "action": "reorder_media",
                "ordered_ids": [self.m1.id, self.m2.id, self.m3.id, other_media.id],
            },
        )
        self.assertEqual(response.status_code, 400)
