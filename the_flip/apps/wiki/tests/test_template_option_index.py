"""Tests for TemplateOptionIndex model and sync_template_option_index function."""

from django.test import TestCase, tag

from the_flip.apps.core.test_utils import TestDataMixin
from the_flip.apps.wiki.actions import sync_template_option_index
from the_flip.apps.wiki.models import TemplateOptionIndex, WikiPage


def _make_content(name="test"):
    return (
        f'<!-- template:start name="{name}" -->\n'
        f"- [ ] step one\n"
        f'<!-- template:end name="{name}" -->\n'
    )


def _make_action(name="test", action="option", record_type="problem", label="Go", **extra):
    machine_attr = f' machine="{extra["machine"]}"' if "machine" in extra else ""
    location_attr = f' location="{extra["location"]}"' if "location" in extra else ""
    priority_attr = f' priority="{extra["priority"]}"' if "priority" in extra else ""
    return (
        f'<!-- template:action name="{name}" action="{action}" type="{record_type}"'
        f'{machine_attr}{location_attr}{priority_attr} label="{label}" -->'
    )


def _make_template(name="test", action="option", record_type="problem", label="Go", **extra):
    return _make_content(name) + _make_action(name, action, record_type, label, **extra)


_page_counter = 0


def _make_page(title=None, content=""):
    global _page_counter
    _page_counter += 1
    if title is None:
        title = f"Index Page {_page_counter}"
    slug = title.lower().replace(" ", "-")
    # post_save signal auto-creates untagged WikiPageTag
    return WikiPage.objects.create(title=title, slug=slug, content=content)


@tag("views")
class SyncTemplateOptionIndexTests(TestCase):
    """Tests for sync_template_option_index()."""

    def test_creates_index_for_option_marker(self):
        page = _make_page(content=_make_template("intake", action="option", record_type="problem"))
        result = sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 1)
        row = TemplateOptionIndex.objects.first()
        self.assertEqual(row.page, page)
        self.assertEqual(row.template_name, "intake")
        self.assertEqual(row.record_type, "problem")
        self.assertEqual(row.label, "Go")
        self.assertTrue(result.changed)
        self.assertEqual(len(result.registered), 1)

    def test_creates_index_for_button_option_marker(self):
        page = _make_page(content=_make_template("intake", action="button,option"))
        sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 1)

    def test_ignores_button_only_marker(self):
        page = _make_page(content=_make_template("intake", action="button"))
        result = sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 0)
        self.assertFalse(result.changed)

    def test_no_markers_creates_no_rows(self):
        page = _make_page(content="Just plain text.")
        result = sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 0)
        self.assertFalse(result.changed)

    def test_multiple_templates_per_page(self):
        content = (
            _make_template("first", action="option", record_type="problem", label="First")
            + "\n"
            + _make_template("second", action="option", record_type="log", label="Second")
        )
        page = _make_page(content=content)
        result = sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 2)
        self.assertEqual(len(result.registered), 2)
        labels = set(TemplateOptionIndex.objects.values_list("label", flat=True))
        self.assertEqual(labels, {"First", "Second"})

    def test_deduplicates_by_name(self):
        """If the same name appears twice, only the first is indexed."""
        content = (
            _make_content("intake")
            + _make_action("intake", action="option", label="First")
            + "\n"
            + _make_action("intake", action="option", label="Second")
        )
        page = _make_page(content=content)
        sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 1)
        self.assertEqual(TemplateOptionIndex.objects.first().label, "First")

    def test_stores_machine_and_location(self):
        page = _make_page(
            content=_make_template(
                "intake", machine="blackout", location="floor-1", label="Floor Checklist"
            )
        )
        sync_template_option_index(page)

        row = TemplateOptionIndex.objects.first()
        self.assertEqual(row.machine_slug, "blackout")
        self.assertEqual(row.location_slug, "floor-1")

    def test_stores_priority(self):
        page = _make_page(content=_make_template("intake", priority="task", label="Task Checklist"))
        sync_template_option_index(page)

        row = TemplateOptionIndex.objects.first()
        self.assertEqual(row.priority, "task")

    def test_rebuild_removes_old_rows(self):
        """Re-syncing replaces old rows, not appends."""
        page = _make_page(content=_make_template("intake", action="option"))
        sync_template_option_index(page)
        self.assertEqual(TemplateOptionIndex.objects.count(), 1)

        # Update page content to remove the template
        page.content = "No templates now."
        page.save()
        result = sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 0)
        self.assertTrue(result.changed)
        self.assertEqual(result.removed_count, 1)

    def test_rebuild_updates_changed_attributes(self):
        page = _make_page(content=_make_template("intake", action="option", label="Old Label"))
        sync_template_option_index(page)
        self.assertEqual(TemplateOptionIndex.objects.first().label, "Old Label")

        page.content = _make_template("intake", action="option", label="New Label")
        page.save()
        sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 1)
        self.assertEqual(TemplateOptionIndex.objects.first().label, "New Label")

    def test_cascade_delete_on_page_delete(self):
        page = _make_page(content=_make_template("intake", action="option"))
        sync_template_option_index(page)
        self.assertEqual(TemplateOptionIndex.objects.count(), 1)

        page.delete()
        self.assertEqual(TemplateOptionIndex.objects.count(), 0)

    def test_invalid_marker_creates_no_rows(self):
        """Markers with invalid attributes are skipped."""
        content = (
            _make_content("intake")
            + '<!-- template:action name="intake" action="option" type="invalid" label="Go" -->'
        )
        page = _make_page(content=content)
        sync_template_option_index(page)

        self.assertEqual(TemplateOptionIndex.objects.count(), 0)


@tag("views")
class SyncCalledOnFormSaveTests(TestDataMixin, TestCase):
    """Verify sync_template_option_index is called via the form save path."""

    def test_form_save_creates_index(self):
        """WikiPageForm.save() should trigger index sync."""
        from the_flip.apps.wiki.forms import WikiPageForm

        form = WikiPageForm(
            data={
                "title": "Template Page",
                "content": _make_template("intake", action="option", label="Intake Check"),
            },
            tags=[],
        )
        self.assertTrue(form.is_valid(), form.errors)
        page = form.save()

        self.assertEqual(TemplateOptionIndex.objects.filter(page=page).count(), 1)
        row = TemplateOptionIndex.objects.get(page=page)
        self.assertEqual(row.template_name, "intake")
        self.assertEqual(row.label, "Intake Check")
        self.assertTrue(hasattr(form, "template_sync_result"))

    def test_form_rejects_broken_template_syntax(self):
        """WikiPageForm rejects content with mismatched template markers."""
        from the_flip.apps.wiki.forms import WikiPageForm

        form = WikiPageForm(
            data={
                "title": "Broken Template Page",
                "content": '<!-- template:start name="oops" -->\ncontent\n',
            },
            tags=[],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("content", form.errors)
