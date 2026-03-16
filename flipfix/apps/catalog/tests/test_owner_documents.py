"""Tests for owner document upload and management."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import Owner, OwnerDocument
from flipfix.apps.core.test_utils import (
    MINIMAL_PNG,
    TemporaryMediaMixin,
    TestDataMixin,
)


def _create_test_owner(**kwargs) -> Owner:
    """Create a test owner with unique name."""
    import uuid

    name = kwargs.pop("name", f"Test Owner {uuid.uuid4().hex[:8]}")
    return Owner.objects.create(name=name, **kwargs)


@tag("models")
class OwnerDocumentModelTests(TestCase):
    """Tests for the OwnerDocument model."""

    def setUp(self):
        self.owner = _create_test_owner()

    def test_display_name_uses_title(self):
        """display_name should return title when set."""
        doc = OwnerDocument(owner=self.owner, title="Insurance Certificate")
        self.assertEqual(doc.display_name, "Insurance Certificate")

    def test_display_name_falls_back_to_filename(self):
        """display_name should use filename when title is blank."""
        doc = OwnerDocument(
            owner=self.owner,
            file=SimpleUploadedFile("contract.pdf", b"fake-pdf"),
        )
        self.assertIn("contract.pdf", doc.display_name)

    def test_is_pdf(self):
        """is_pdf should be True for .pdf files."""
        doc = OwnerDocument(
            owner=self.owner,
            file=SimpleUploadedFile("doc.pdf", b"fake"),
        )
        self.assertTrue(doc.is_pdf)

    def test_is_image(self):
        """is_image should be True for image extensions."""
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            doc = OwnerDocument(
                owner=self.owner,
                file=SimpleUploadedFile(f"photo{ext}", b"fake"),
            )
            self.assertTrue(doc.is_image, f"Expected is_image=True for {ext}")

    def test_is_not_image_for_pdf(self):
        """is_image should be False for PDF files."""
        doc = OwnerDocument(
            owner=self.owner,
            file=SimpleUploadedFile("doc.pdf", b"fake"),
        )
        self.assertFalse(doc.is_image)


@tag("forms")
class OwnerDocumentFormTests(TestCase):
    """Tests for OwnerDocumentForm validation."""

    def test_accepts_pdf(self):
        """Form should accept PDF files."""
        from flipfix.apps.catalog.forms import OwnerDocumentForm

        form = OwnerDocumentForm(
            data={"title": "Test"},
            files={"file": SimpleUploadedFile("test.pdf", b"fake-pdf-content")},
        )
        self.assertTrue(form.is_valid())

    def test_accepts_image(self):
        """Form should accept image files."""
        from flipfix.apps.catalog.forms import OwnerDocumentForm

        form = OwnerDocumentForm(
            data={"title": ""},
            files={"file": SimpleUploadedFile("photo.jpg", MINIMAL_PNG)},
        )
        self.assertTrue(form.is_valid())

    def test_rejects_executable(self):
        """Form should reject disallowed file types."""
        from flipfix.apps.catalog.forms import OwnerDocumentForm

        form = OwnerDocumentForm(
            data={"title": ""},
            files={"file": SimpleUploadedFile("malware.exe", b"bad-content")},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_rejects_shell_script(self):
        """Form should reject .sh files."""
        from flipfix.apps.catalog.forms import OwnerDocumentForm

        form = OwnerDocumentForm(
            data={"title": ""},
            files={"file": SimpleUploadedFile("script.sh", b"#!/bin/bash")},
        )
        self.assertFalse(form.is_valid())


@tag("views")
class OwnerDocumentUploadTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for document upload via the owner detail view."""

    def setUp(self):
        super().setUp()
        self.owner = _create_test_owner()
        self.url = reverse("owner-detail", kwargs={"slug": self.owner.slug})

    def test_upload_document(self):
        """POST with upload_document action should create a document."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.url,
            {
                "action": "upload_document",
                "title": "Test Doc",
                "file": SimpleUploadedFile("test.pdf", b"pdf-content"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.owner.documents.count(), 1)
        doc = self.owner.documents.first()
        self.assertEqual(doc.title, "Test Doc")
        self.assertEqual(doc.uploaded_by, self.maintainer_user)

    def test_delete_document(self):
        """POST with delete_document action should remove the document."""
        self.client.force_login(self.maintainer_user)
        doc = OwnerDocument.objects.create(
            owner=self.owner,
            file=SimpleUploadedFile("to-delete.pdf", b"content"),
        )
        response = self.client.post(
            self.url,
            {"action": "delete_document", "document_id": doc.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.owner.documents.count(), 0)

    def test_documents_listed_on_detail(self):
        """Documents should appear on the owner detail page."""
        OwnerDocument.objects.create(
            owner=self.owner,
            title="Visible Doc",
            file=SimpleUploadedFile("visible.pdf", b"content"),
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertContains(response, "Visible Doc")
