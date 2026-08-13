"""Tests for the part request status-change vocabulary in parts/status_log.py."""

from django.test import SimpleTestCase, tag

from flipfix.apps.parts.status_log import status_change_comment, status_change_text


@tag("models")
class StatusChangeCommentTests(SimpleTestCase):
    def test_bare_status_change_has_no_comment(self):
        self.assertEqual(status_change_comment(status_change_text("Requested", "Ordered")), "")

    def test_comment_after_a_status_change_is_returned(self):
        text = f"{status_change_text('Requested', 'Ordered')}\nPinball Life order 02-1447"
        self.assertEqual(status_change_comment(text), "Pinball Life order 02-1447")

    def test_windows_line_endings_are_handled(self):
        text = f"{status_change_text('Ordered', 'Received')}\r\n\r\nGlass was etched, returning it"
        self.assertEqual(status_change_comment(text), "Glass was etched, returning it")

    def test_plain_comment_is_all_comment(self):
        text = "Did the cotter pins come in?"
        self.assertEqual(status_change_comment(text), text)

    def test_empty_text(self):
        self.assertEqual(status_change_comment(""), "")
