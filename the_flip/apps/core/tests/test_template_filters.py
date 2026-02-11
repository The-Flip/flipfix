"""Tests for template filters."""

from django.test import TestCase, tag

from the_flip.apps.accounts.templatetags.accounts_tags import display_name_with_username
from the_flip.apps.catalog.templatetags.catalog_tags import (
    machine_status_btn_class,
    machine_status_css_class,
    machine_status_icon,
)
from the_flip.apps.core.test_utils import create_user


@tag("views")
class DisplayNameWithUsernameFilterTests(TestCase):
    """Tests for the display_name_with_username template filter."""

    def test_none_returns_empty_string(self):
        """None input returns empty string."""
        self.assertEqual(display_name_with_username(None), "")

    def test_username_only(self):
        """User with no name returns just username."""
        user = create_user(username="jsmith")
        self.assertEqual(display_name_with_username(user), "jsmith")

    def test_first_name_only(self):
        """User with only first name returns 'First (username)'."""
        user = create_user(username="jsmith", first_name="John")
        self.assertEqual(display_name_with_username(user), "John (jsmith)")

    def test_last_name_only(self):
        """User with only last name returns 'Last (username)'."""
        user = create_user(username="jsmith", last_name="Smith")
        self.assertEqual(display_name_with_username(user), "Smith (jsmith)")

    def test_full_name(self):
        """User with full name returns 'First Last (username)'."""
        user = create_user(username="jsmith", first_name="John", last_name="Smith")
        self.assertEqual(display_name_with_username(user), "John Smith (jsmith)")


@tag("views")
class MachineStatusFilterTests(TestCase):
    """Tests for MachineInstance.operational_status template filters."""

    def test_machine_status_css_class_good(self):
        """Good status returns pill--status-good."""
        self.assertEqual(machine_status_css_class("good"), "pill--status-good")

    def test_machine_status_css_class_fixing(self):
        """Fixing status returns pill--status-fixing."""
        self.assertEqual(machine_status_css_class("fixing"), "pill--status-fixing")

    def test_machine_status_css_class_broken(self):
        """Broken status returns pill--status-broken."""
        self.assertEqual(machine_status_css_class("broken"), "pill--status-broken")

    def test_machine_status_css_class_unknown(self):
        """Unknown status returns pill--neutral."""
        self.assertEqual(machine_status_css_class("unknown"), "pill--neutral")

    def test_machine_status_css_class_fallback(self):
        """Unrecognized status returns pill--neutral."""
        self.assertEqual(machine_status_css_class("invalid"), "pill--neutral")
        self.assertEqual(machine_status_css_class(""), "pill--neutral")
        self.assertEqual(machine_status_css_class(None), "pill--neutral")

    def test_machine_status_icon_good(self):
        """Good status returns check icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("good"), "check")

    def test_machine_status_icon_fixing(self):
        """Fixing status returns wrench icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("fixing"), "wrench")

    def test_machine_status_icon_broken(self):
        """Broken status returns circle-xmark icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("broken"), "circle-xmark")

    def test_machine_status_icon_unknown(self):
        """Unknown status returns circle-question icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("unknown"), "circle-question")

    def test_machine_status_icon_fallback(self):
        """Unrecognized status returns circle-question icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("invalid"), "circle-question")
        self.assertEqual(machine_status_icon(""), "circle-question")
        self.assertEqual(machine_status_icon(None), "circle-question")

    def test_machine_status_btn_class_good(self):
        """Good status returns btn--status-good."""
        self.assertEqual(machine_status_btn_class("good"), "btn--status-good")

    def test_machine_status_btn_class_fixing(self):
        """Fixing status returns btn--status-fixing."""
        self.assertEqual(machine_status_btn_class("fixing"), "btn--status-fixing")

    def test_machine_status_btn_class_broken(self):
        """Broken status returns btn--status-broken."""
        self.assertEqual(machine_status_btn_class("broken"), "btn--status-broken")

    def test_machine_status_btn_class_unknown(self):
        """Unknown status returns btn--secondary."""
        self.assertEqual(machine_status_btn_class("unknown"), "btn--secondary")

    def test_machine_status_btn_class_fallback(self):
        """Unrecognized status returns btn--secondary."""
        self.assertEqual(machine_status_btn_class("invalid"), "btn--secondary")
        self.assertEqual(machine_status_btn_class(""), "btn--secondary")
        self.assertEqual(machine_status_btn_class(None), "btn--secondary")
