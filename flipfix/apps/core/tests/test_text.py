"""Tests for core text utilities."""

from django.test import TestCase, tag

from flipfix.apps.core.text import strip_leading_articles


@tag("unit")
class StripLeadingArticlesTests(TestCase):
    """Tests for strip_leading_articles()."""

    def test_strips_the(self):
        self.assertEqual(strip_leading_articles("The Addams Family"), "Addams Family")

    def test_strips_a(self):
        self.assertEqual(strip_leading_articles("A New Machine"), "New Machine")

    def test_strips_an(self):
        self.assertEqual(strip_leading_articles("An Old Game"), "Old Game")

    def test_case_insensitive(self):
        self.assertEqual(strip_leading_articles("the addams family"), "addams family")
        self.assertEqual(strip_leading_articles("THE ADDAMS FAMILY"), "ADDAMS FAMILY")

    def test_no_op_aerosmith(self):
        """'Aerosmith' should not be affected — 'A' needs a trailing space."""
        self.assertEqual(strip_leading_articles("Aerosmith"), "Aerosmith")

    def test_no_op_andromeda(self):
        """'Andromeda' should not be affected — 'An' needs a trailing space."""
        self.assertEqual(strip_leading_articles("Andromeda"), "Andromeda")

    def test_no_op_theatre_of_magic(self):
        """'Theatre of Magic' should not be affected — 'The' needs exact match."""
        self.assertEqual(strip_leading_articles("Theatre of Magic"), "Theatre of Magic")

    def test_empty_string(self):
        self.assertEqual(strip_leading_articles(""), "")

    def test_name_is_just_the_article(self):
        """If the name is just 'The', return it unchanged."""
        self.assertEqual(strip_leading_articles("The"), "The")

    def test_no_article(self):
        self.assertEqual(strip_leading_articles("Monster Bash"), "Monster Bash")

    def test_article_only_stripped_from_start(self):
        """Articles in the middle of the name should not be stripped."""
        self.assertEqual(strip_leading_articles("Escape The Room"), "Escape The Room")
