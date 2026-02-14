"""Tests for parts forms."""

from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, tag

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_part_request,
    create_part_request_update,
)
from the_flip.apps.parts.forms import (
    PartRequestEditForm,
    PartRequestForm,
    PartRequestUpdateEditForm,
)


@tag("forms")
class PartRequestEditFormTests(TestDataMixin, TestCase):
    """Tests for PartRequestEditForm validation.

    Note: Future date validation is tested in test_part_request_edit.py
    as a view test, since validation happens after timezone conversion
    in form_valid().
    """

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )

    def test_occurred_at_is_required(self):
        """Form requires occurred_at field."""
        form = PartRequestEditForm(
            data={"occurred_at": ""},
            instance=self.part_request,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)


@tag("forms")
class PartRequestUpdateEditFormTests(TestDataMixin, TestCase):
    """Tests for PartRequestUpdateEditForm validation.

    Note: Future date validation is tested in test_part_request_edit.py
    as a view test, since validation happens after timezone conversion
    in form_valid().
    """

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.update = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Test update",
        )

    def test_occurred_at_is_required(self):
        """Form requires occurred_at field."""
        form = PartRequestUpdateEditForm(
            data={"occurred_at": ""},
            instance=self.update,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)


@tag("forms")
class PartRequestFormMarkdownTests(TestDataMixin, TestCase):
    """Tests for markdown link conversion in PartRequestForm."""

    def test_text_converts_authoring_links_to_storage(self):
        """Authoring-format [[links]] in text are converted to storage format."""
        form = PartRequestForm(
            data={
                "text": f"Need part for [[machine:{self.machine.slug}]]",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(f"[[machine:id:{self.machine.pk}]]", form.cleaned_data["text"])


@tag("forms")
class PartRequestFormOccurredAtTests(TestCase):
    """Tests for occurred_at defaulting in PartRequestForm."""

    @mock.patch("the_flip.apps.core.forms.timezone.now")
    def test_defaults_to_now_when_empty(self, mock_now):
        """Empty occurred_at defaults to timezone.now()."""
        fixed = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        mock_now.return_value = fixed

        form = PartRequestForm(
            data={
                "text": "Need a new flipper",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["occurred_at"], fixed)
