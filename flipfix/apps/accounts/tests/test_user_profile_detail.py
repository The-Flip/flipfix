"""Tests for the ``/users/<username>/`` profile detail view.

The visibility predicate lives in ``test_user_directory_predicates.py``;
this module verifies the detail view enforces the same predicate (404
otherwise), gates access via ``can_view_user_profiles``, renders the
bio as markdown, and links the breadcrumb back to the directory.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.accounts.models import MaintainerMedia
from flipfix.apps.core.test_utils import (
    MINIMAL_PNG,
    TemporaryMediaMixin,
    create_maintainer_user,
    create_user,
)


def _profile_url(username: str) -> str:
    return reverse("user-profile", kwargs={"username": username})


@tag("views")
class UserProfileAccessTests(TestCase):
    """Who can reach ``/users/<username>/``."""

    def setUp(self):
        self.target = create_maintainer_user(username="alice", first_name="Alice")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(_profile_url("alice"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_non_maintainer_forbidden(self):
        """``MaintainerAccessMiddleware`` rejects the request before the view runs."""
        user = create_user(username="visitor")
        self.client.force_login(user)
        response = self.client.get(_profile_url("alice"))
        self.assertEqual(response.status_code, 403)

    def test_maintainer_can_view(self):
        viewer = create_maintainer_user(username="viewer")
        self.client.force_login(viewer)
        response = self.client.get(_profile_url("alice"))
        self.assertEqual(response.status_code, 200)


@tag("views")
class UserProfileDirectoryParityTests(TestCase):
    """A profile only renders for users who appear in the directory.

    Mirrors the predicate test cases from ``UserDirectoryContentTests``
    — same exclusions, asserted from the other angle (404 instead of
    absence from the listing).
    """

    def setUp(self):
        self.viewer = create_maintainer_user(username="viewer")
        self.client.force_login(self.viewer)

    def test_inactive_user_404(self):
        target = create_maintainer_user(username="bob")
        target.is_active = False
        target.save()
        response = self.client.get(_profile_url("bob"))
        self.assertEqual(response.status_code, 404)

    def test_shared_account_404(self):
        target = create_maintainer_user(username="kiosk")
        target.maintainer.is_shared_account = True
        target.maintainer.save()
        response = self.client.get(_profile_url("kiosk"))
        self.assertEqual(response.status_code, 404)

    def test_non_maintainer_404(self):
        create_user(username="orphan")
        response = self.client.get(_profile_url("orphan"))
        self.assertEqual(response.status_code, 404)

    def test_unknown_username_404(self):
        response = self.client.get(_profile_url("nobody"))
        self.assertEqual(response.status_code, 404)


@tag("views")
class UserProfileContentTests(TestCase):
    """What the profile page shows."""

    def setUp(self):
        self.viewer = create_maintainer_user(username="viewer")
        self.client.force_login(self.viewer)
        self.target = create_maintainer_user(
            username="alice", first_name="Alice", last_name="Anderson"
        )

    def test_display_name_with_username_in_title(self):
        response = self.client.get(_profile_url("alice"))
        self.assertContains(response, "Alice Anderson (alice)")

    def test_breadcrumb_links_to_directory(self):
        response = self.client.get(_profile_url("alice"))
        self.assertContains(response, f'href="{reverse("user-directory")}"')
        self.assertContains(response, ">Users</a>")

    def test_breadcrumb_uses_full_display_name(self):
        """The current-page breadcrumb segment is the full display name, not bare username."""
        response = self.client.get(_profile_url("alice"))
        self.assertContains(response, "<span>Alice Anderson (alice)</span>")

    def test_full_bio_rendered_as_markdown(self):
        """Detail page renders the *full* bio (not truncated like the card)."""
        self.target.maintainer.bio = "**Bold** and _italic_."
        self.target.maintainer.save()
        response = self.client.get(_profile_url("alice"))
        self.assertContains(response, "<strong>Bold</strong>")
        self.assertContains(response, "<em>italic</em>")

    def test_empty_bio_section_omitted(self):
        response = self.client.get(_profile_url("alice"))
        # Section only renders when bio is set; the wrapper class is the
        # unique tell.
        self.assertNotContains(response, "user-profile__bio")

    def test_media_section_omitted_when_empty(self):
        """No media → no media section at all (no stranded silhouette tile)."""
        response = self.client.get(_profile_url("alice"))
        self.assertNotContains(response, "user-profile__media")

    def test_directory_card_links_to_profile(self):
        """Regression guard: directory cards link via {% url 'user-profile' %}."""
        response = self.client.get(reverse("user-directory"))
        self.assertContains(response, f'href="{_profile_url("alice")}"')


@tag("views")
class UserProfileMediaRenderTests(TemporaryMediaMixin, TestCase):
    """Photo and video media render with the right tags.

    Uses ``TemporaryMediaMixin`` so the uploaded files don't pollute
    ``MEDIA_ROOT``. Photos exercise the ``<img>`` branch; videos
    exercise the shared ``video_player`` component.
    """

    def setUp(self):
        self.viewer = create_maintainer_user(username="viewer")
        self.client.force_login(self.viewer)
        self.target = create_maintainer_user(username="alice", first_name="Alice")

    def test_photo_rendered_as_img(self):
        MaintainerMedia.objects.create(
            maintainer=self.target.maintainer,
            media_type=MaintainerMedia.MediaType.PHOTO,
            file=SimpleUploadedFile("p.png", MINIMAL_PNG, content_type="image/png"),
        )
        response = self.client.get(_profile_url("alice"))
        self.assertContains(response, 'class="user-profile__photo"')

    def test_video_rendered_via_video_player(self):
        MaintainerMedia.objects.create(
            maintainer=self.target.maintainer,
            media_type=MaintainerMedia.MediaType.VIDEO,
            file=SimpleUploadedFile("v.mp4", b"fake-video-bytes", content_type="video/mp4"),
        )
        response = self.client.get(_profile_url("alice"))
        # Fresh upload starts in PENDING transcode status, so video_player
        # renders the processing-status placeholder rather than the <video> tag.
        # Either way, the tell is that the video_player branch executed.
        self.assertContains(response, 'data-media-poll-model="MaintainerMedia"')
