"""Tests for maintenance forms."""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    DATETIME_INPUT_FORMAT,
    MINIMAL_PNG,
    TestDataMixin,
    create_log_entry,
    create_problem_report,
)
from the_flip.apps.maintenance.forms import (
    LogEntryEditForm,
    LogEntryQuickForm,
    MaintainerProblemReportForm,
    ProblemReportEditForm,
)


@tag("forms")
class LogEntryQuickFormMediaValidationTests(TestCase):
    """Tests for media file validation in LogEntryQuickForm."""

    def _form_data(self, media_file=None):
        """Helper to create valid form data."""
        from django.utils import timezone

        data = {
            "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
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


@tag("forms")
class ProblemReportEditFormTests(TestDataMixin, TestCase):
    """Tests for ProblemReportEditForm validation.

    Note: Future date validation is tested in test_problem_report_edit.py
    as a view test, since validation happens after timezone conversion
    in form_valid().
    """

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(machine=self.machine)

    def test_occurred_at_is_required(self):
        """Form requires occurred_at field."""
        form = ProblemReportEditForm(
            data={"occurred_at": ""},
            instance=self.problem_report,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)


@tag("forms")
class LogEntryEditFormTests(TestDataMixin, TestCase):
    """Tests for LogEntryEditForm validation.

    Note: Future date validation is tested in test_log_entry_edit.py
    as a view test, since validation happens after timezone conversion
    in form_valid().
    """

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine)
        self.log_entry.maintainers.add(self.maintainer)

    def test_occurred_at_is_required(self):
        """Form requires occurred_at field."""
        form = LogEntryEditForm(
            data={"occurred_at": ""},
            instance=self.log_entry,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)


@tag("forms")
class MaintainerProblemReportFormMarkdownTests(TestDataMixin, TestCase):
    """Tests for markdown link conversion in MaintainerProblemReportForm."""

    def test_description_converts_authoring_links_to_storage(self):
        """Authoring-format [[links]] in description are converted to storage format."""
        form = MaintainerProblemReportForm(
            data={
                "description": f"See [[machine:{self.machine.slug}]]",
                "priority": "minor",
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(f"[[machine:id:{self.machine.pk}]]", form.cleaned_data["description"])


@tag("forms")
class LogEntryQuickFormOccurredAtTests(TestCase):
    """Tests for occurred_at validation in LogEntryQuickForm."""

    def test_rejects_future_date(self):
        """Form rejects occurred_at dates in the future."""
        future = timezone.now() + timedelta(days=2)
        form = LogEntryQuickForm(
            data={
                "occurred_at": future.strftime(DATETIME_INPUT_FORMAT),
                "text": "Some work",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)
        self.assertIn("future", form.errors["occurred_at"][0])
