"""Tests for maintenance forms."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from the_flip.apps.core.test_utils import DATETIME_INPUT_FORMAT, MINIMAL_PNG
from the_flip.apps.maintenance.forms import LogEntryQuickForm


@tag("forms")
class LogEntryQuickFormMediaValidationTests(TestCase):
    """Tests for media file validation in LogEntryQuickForm."""

    def _form_data(self, media_file=None):
        """Helper to create valid form data."""
        from django.utils import timezone

        data = {
            "work_date": timezone.now().strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        # Accept either a single file or a list of files
        if media_file:
            if isinstance(media_file, list | tuple):
                files = {"media_file": media_file}
            else:
                files = {"media_file": [media_file]}
        else:
            files = {}
        return data, files

    def test_rejects_executable_file(self):
        """Form should reject executable files (.exe)."""
        exe_file = SimpleUploadedFile(
            "malware.exe", b"MZ\x90\x00executable content", content_type="application/x-msdownload"
        )
        data, files = self._form_data(exe_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertFalse(form.is_valid())
        self.assertIn("media_file", form.errors)
        self.assertIn("valid image or video", form.errors["media_file"][0])

    def test_rejects_shell_script(self):
        """Form should reject shell scripts (.sh)."""
        sh_file = SimpleUploadedFile(
            "script.sh", b"#!/bin/bash\nrm -rf /", content_type="application/x-sh"
        )
        data, files = self._form_data(sh_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertFalse(form.is_valid())
        self.assertIn("media_file", form.errors)

    def test_rejects_html_file(self):
        """Form should reject HTML files (potential XSS vector)."""
        html_file = SimpleUploadedFile(
            "page.html", b"<script>alert('xss')</script>", content_type="text/html"
        )
        data, files = self._form_data(html_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertFalse(form.is_valid())
        self.assertIn("media_file", form.errors)

    def test_accepts_valid_image(self):
        """Form should accept valid image files."""
        png_file = SimpleUploadedFile("photo.png", MINIMAL_PNG, content_type="image/png")
        data, files = self._form_data(png_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertTrue(form.is_valid(), form.errors)

    def test_accepts_valid_video(self):
        """Form should accept video files."""
        video_file = SimpleUploadedFile("clip.mp4", b"fake video content", content_type="video/mp4")
        data, files = self._form_data(video_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertTrue(form.is_valid(), form.errors)

    def test_accepts_multiple_files(self):
        """Form should accept multiple files at once."""
        png_file = SimpleUploadedFile("photo.png", MINIMAL_PNG, content_type="image/png")
        video_file = SimpleUploadedFile("clip.mp4", b"fake video content", content_type="video/mp4")

        data, files = self._form_data([png_file, video_file])
        form = LogEntryQuickForm(data=data, files=files)

        self.assertTrue(form.is_valid(), form.errors)
        media_list = form.cleaned_data["media_file"]
        self.assertEqual(len(media_list), 2)

    def test_rejects_oversized_file(self):
        """Form should reject files over 200MB."""
        # Create a file that claims to be over 200MB
        large_file = SimpleUploadedFile("huge.mp4", b"x", content_type="video/mp4")
        large_file.size = 201 * 1024 * 1024  # 201MB

        data, files = self._form_data(large_file)
        form = LogEntryQuickForm(data=data, files=files)

        self.assertFalse(form.is_valid())
        self.assertIn("media_file", form.errors)
        self.assertIn("200MB", form.errors["media_file"][0])
