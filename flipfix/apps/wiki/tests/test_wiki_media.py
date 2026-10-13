"""Tests for inline wiki images: upload, references, and orphan cleanup."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TemporaryMediaMixin,
    TestDataMixin,
    create_uploaded_image,
)
from flipfix.apps.wiki.media import (
    ORPHAN_GRACE_PERIOD,
    alt_text_from_filename,
    create_wiki_image,
    delete_orphaned_media,
    media_markdown,
    referenced_media_ids,
)
from flipfix.apps.wiki.models import WikiMedia, WikiPage, wiki_media_upload_to
from flipfix.apps.wiki.tasks import delete_orphaned_wiki_media


def _jpeg_upload(name: str = "photo.jpg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, create_uploaded_image().read(), content_type="image/jpeg")


def _backdate(media: WikiMedia, age: timedelta) -> None:
    """Age media past (or within) the orphan grace period."""
    WikiMedia.objects.filter(pk=media.pk).update(created_at=timezone.now() - age)


@tag("views")
class WikiMediaUploadViewTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for the inline image upload endpoint."""

    def setUp(self):
        super().setUp()
        self.url = reverse("api-wiki-media-upload")

    def test_upload_creates_unlinked_media_and_returns_markdown(self):
        """An upload without a page creates an image no page links to yet."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(self.url, {"file": _jpeg_upload("belt_drive.jpg")})

        self.assertEqual(response.status_code, 200)
        image = WikiMedia.objects.get()
        self.assertEqual(
            response.json(),
            {"success": True, "markdown": f"![belt drive]({image.get_absolute_url()})"},
        )
        self.assertFalse(image.pages.exists())
        self.assertEqual(image.uploaded_by, self.maintainer_user)

    def test_upload_with_page_links_media(self):
        """An upload from the edit page links the image to that page."""
        self.client.force_login(self.maintainer_user)
        page = WikiPage.objects.create(title="Guide", slug="guide")

        self.client.post(self.url, {"file": _jpeg_upload(), "page": page.pk})

        self.assertEqual(list(WikiMedia.objects.get().pages.all()), [page])

    def test_rejects_video(self):
        """Videos are rejected."""
        self.client.force_login(self.maintainer_user)
        video = SimpleUploadedFile("clip.mp4", b"not really video", content_type="video/mp4")

        response = self.client.post(self.url, {"file": video})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertFalse(WikiMedia.objects.exists())

    def test_rejects_non_image(self):
        """Files that aren't images are rejected."""
        self.client.force_login(self.maintainer_user)
        text = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")

        response = self.client.post(self.url, {"file": text})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Upload a valid image.")

    def test_rejects_oversize_image(self):
        """Images over the wiki size cap are rejected."""
        self.client.force_login(self.maintainer_user)

        with patch("flipfix.apps.wiki.forms.MAX_WIKI_IMAGE_BYTES", 10):
            response = self.client.post(self.url, {"file": _jpeg_upload()})

        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", response.json()["error"])
        self.assertFalse(WikiMedia.objects.exists())

    def test_rejects_missing_file(self):
        """A request with no file is rejected."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.post(self.url, {"file": _jpeg_upload()})

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_requires_maintainer(self):
        """Non-maintainer users get 403."""
        self.client.force_login(self.regular_user)

        response = self.client.post(self.url, {"file": _jpeg_upload()})

        self.assertEqual(response.status_code, 403)


@tag("views")
class WikiMediaViewTests(TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the stable image URL."""

    def test_redirects_to_stored_file(self):
        """The stable URL redirects to the stored file."""
        self.client.force_login(self.maintainer_user)
        image = create_wiki_image(file=_jpeg_upload(), uploaded_by=None)

        response = self.client.get(image.get_absolute_url())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, image.file.url)

    def test_redirect_is_cached_privately(self):
        """Browsers may cache the redirect, but shared caches may not."""
        self.client.force_login(self.maintainer_user)
        image = create_wiki_image(file=_jpeg_upload(), uploaded_by=None)

        response = self.client.get(image.get_absolute_url())

        self.assertEqual(response["Cache-Control"], "private, max-age=86400")

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        image = create_wiki_image(file=_jpeg_upload(), uploaded_by=None)

        response = self.client.get(image.get_absolute_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_unknown_media_returns_404(self):
        """An unknown id returns 404."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("wiki-media", kwargs={"pk": 999999}))

        self.assertEqual(response.status_code, 404)


@tag("views")
class WikiMediaReferenceTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Saving a page links the images its content references."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.maintainer_user)
        self.image = create_wiki_image(file=_jpeg_upload(), uploaded_by=None)
        self.markdown = media_markdown(self.image, "photo")

    def _create_page(self, title: str, content: str) -> WikiPage:
        response = self.client.post(
            reverse("wiki-page-create"), {"title": title, "content": content}
        )
        self.assertEqual(response.status_code, 302)
        return WikiPage.objects.get(title=title)

    def test_creating_page_links_referenced_media(self):
        """Creating a page links an image uploaded before the page existed."""
        page = self._create_page("Guide", f"Intro\n\n{self.markdown}")

        self.assertEqual(list(self.image.pages.all()), [page])

    def test_media_can_belong_to_several_pages(self):
        """Pasting an image's markdown into a second page links that page too."""
        first = self._create_page("First", self.markdown)
        second = self._create_page("Second", self.markdown)

        self.assertEqual(set(self.image.pages.all()), {first, second})

    def test_removing_reference_keeps_link(self):
        """Editing an image out of a page keeps the link, so old revisions still render."""
        page = self._create_page("Guide", self.markdown)

        self.client.post(
            reverse("wiki-page-edit", args=["guide"]),
            {"title": "Guide", "content": "No more images"},
        )

        self.assertEqual(list(self.image.pages.all()), [page])

    def test_inline_edit_links_referenced_media(self):
        """Saving content from the detail page's inline editor links images too."""
        page = WikiPage.objects.create(title="Guide", slug="guide")

        self.client.post(
            reverse("wiki-page-detail", args=["guide"]),
            {"action": "update_text", "text": self.markdown},
        )

        self.assertEqual(list(self.image.pages.all()), [page])

    def test_unknown_media_ids_are_ignored(self):
        """References to images that don't exist don't break saving."""
        page = self._create_page("Guide", "![gone](/wiki/media/999999/)")

        self.assertFalse(page.media.exists())

    def test_edit_form_configures_image_upload(self):
        """The edit form's textarea carries the upload URL and page id."""
        page = self._create_page("Guide", "")

        response = self.client.get(reverse("wiki-page-edit", args=["guide"]))

        self.assertContains(response, f'data-image-upload-url="{reverse("api-wiki-media-upload")}"')
        self.assertContains(response, f'data-image-upload-page="{page.pk}"')


@tag("models")
class WikiMediaHelperTests(TestCase):
    """Tests for the pure helpers."""

    def test_referenced_media_ids(self):
        """Ids are parsed from relative and absolute image URLs."""
        content = (
            "![a](/wiki/media/3/) and ![b](https://flipfix.example/wiki/media/12/)"
            " but not [[page:wiki]] or /wiki/edit/images"
        )

        self.assertEqual(referenced_media_ids(content), {3, 12})

    def test_storage_name_fits_the_file_field(self):
        """Overlong client file names (stem or extension) are bounded for storage.

        Django's storage can shorten a long stem but not an extension, so an
        unbounded name could raise SuspiciousFileOperation on save.
        """
        max_length = WikiMedia._meta.get_field("file").max_length

        for name in (f"{'s' * 300}.jpg", f"photo.{'e' * 200}", "Belt Drive (1).JPG"):
            with self.subTest(name=name[:20]):
                path = wiki_media_upload_to(WikiMedia(), name)
                self.assertLessEqual(len(path), max_length)
                self.assertTrue(path.startswith("wiki/"))

        self.assertTrue(
            wiki_media_upload_to(WikiMedia(), "Belt Drive (1).JPG").endswith("-belt-drive-1.jpg")
        )

    def test_alt_text_from_filename(self):
        """File names become readable alt text."""
        self.assertEqual(alt_text_from_filename("left_flipper-coil.JPG"), "left flipper coil")
        self.assertEqual(alt_text_from_filename("__.png"), "image")

    def test_media_markdown_strips_brackets_from_alt(self):
        """Brackets can't break out of the alt text."""
        image = WikiMedia(pk=7)

        self.assertEqual(media_markdown(image, "a [b] c"), "![a b c](/wiki/media/7/)")


@tag("tasks")
class DeleteOrphanedMediaTests(TemporaryMediaMixin, TestCase):
    """Tests for the orphan sweep."""

    def setUp(self):
        super().setUp()
        self.page_a = WikiPage.objects.create(title="A", slug="a")
        self.page_b = WikiPage.objects.create(title="B", slug="b")

    def _media(self, *pages: WikiPage, age: timedelta = ORPHAN_GRACE_PERIOD * 2) -> WikiMedia:
        image = create_wiki_image(file=_jpeg_upload(), uploaded_by=None)
        image.pages.add(*pages)
        _backdate(image, age)
        return image

    def _sweep(self) -> int:
        with self.captureOnCommitCallbacks(execute=True):
            return delete_orphaned_media()

    def test_deletes_old_unlinked_media_and_files(self):
        """An image no page ever used is deleted, with its files, after the grace period."""
        image = self._media()
        names = [image.file.name]

        self.assertEqual(self._sweep(), 1)

        self.assertFalse(WikiMedia.objects.filter(pk=image.pk).exists())
        for name in names:
            self.assertFalse(default_storage.exists(name))

    def test_keeps_recent_unlinked_media(self):
        """A fresh upload survives, so a page being created has time to be saved."""
        image = self._media(age=timedelta(minutes=5))

        self.assertEqual(self._sweep(), 0)

        self.assertTrue(WikiMedia.objects.filter(pk=image.pk).exists())

    def test_keeps_media_still_used_by_another_page(self):
        """Deleting page A keeps an image page B also uses."""
        image = self._media(self.page_a, self.page_b)

        self.page_a.delete()
        self._sweep()

        self.assertTrue(WikiMedia.objects.filter(pk=image.pk).exists())
        self.assertTrue(default_storage.exists(image.file.name))

    def test_deletes_media_when_its_last_page_is_deleted(self):
        """Once every page that used an image is gone, the sweep removes it."""
        image = self._media(self.page_a)

        self.page_a.delete()

        self.assertEqual(self._sweep(), 1)
        self.assertFalse(WikiMedia.objects.filter(pk=image.pk).exists())
        self.assertFalse(default_storage.exists(image.file.name))

    def test_links_instead_of_deleting_media_a_page_still_embeds(self):
        """Safety net: media embedded in current content survives even if never linked.

        Guards against a code path that saves page content without calling
        record_media_references.
        """
        image = self._media()
        WikiPage.objects.filter(pk=self.page_b.pk).update(
            content=f"![x]({image.get_absolute_url()})"
        )

        self.assertEqual(self._sweep(), 0)

        self.assertEqual(list(image.pages.all()), [self.page_b])
        self.assertTrue(default_storage.exists(image.file.name))

    def test_scheduled_task_runs_the_sweep(self):
        """The django-q entry point deletes orphans and returns the count."""
        self._media()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(delete_orphaned_wiki_media(), 1)
