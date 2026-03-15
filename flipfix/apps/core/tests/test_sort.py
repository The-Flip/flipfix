"""Tests for article-stripping sort utility."""

from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineModel
from flipfix.apps.core.sort import article_sort_key


@tag("models")
class ArticleSortKeyTests(TestCase):
    """Tests for article_sort_key database annotation."""

    def _sorted_names(self, field="name"):
        """Return model names sorted by article_sort_key."""
        return list(
            MachineModel.objects.annotate(sort_name=article_sort_key(field))
            .order_by("sort_name")
            .values_list("name", flat=True)
        )

    def test_the_sorts_under_next_word(self):
        """'The Addams Family' should sort under A, not T."""
        MachineModel.objects.create(name="Twilight Zone")
        MachineModel.objects.create(name="The Addams Family")
        MachineModel.objects.create(name="Bally Star Trek")

        result = self._sorted_names()
        self.assertEqual(result, ["The Addams Family", "Bally Star Trek", "Twilight Zone"])

    def test_a_sorts_under_next_word(self):
        """'A Game' should sort under G."""
        MachineModel.objects.create(name="A Game")
        MachineModel.objects.create(name="Bally")

        result = self._sorted_names()
        self.assertEqual(result, ["Bally", "A Game"])

    def test_an_sorts_under_next_word(self):
        """'An Example' should sort under E."""
        MachineModel.objects.create(name="An Example")
        MachineModel.objects.create(name="Fireball")

        result = self._sorted_names()
        self.assertEqual(result, ["An Example", "Fireball"])

    def test_case_insensitive(self):
        """Article stripping should be case-insensitive."""
        MachineModel.objects.create(name="THE MACHINE")
        MachineModel.objects.create(name="Alpha")

        result = self._sorted_names()
        self.assertEqual(result, ["Alpha", "THE MACHINE"])

    def test_no_article_unaffected(self):
        """Names without articles sort normally."""
        MachineModel.objects.create(name="Zebra")
        MachineModel.objects.create(name="Alpha")

        result = self._sorted_names()
        self.assertEqual(result, ["Alpha", "Zebra"])

    def test_the_in_middle_not_stripped(self):
        """'Bathe' should not have 'the' stripped (not a prefix)."""
        MachineModel.objects.create(name="Bathe")
        MachineModel.objects.create(name="Alpha")

        result = self._sorted_names()
        self.assertEqual(result, ["Alpha", "Bathe"])
