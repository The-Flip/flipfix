"""Tests for wiki template list and content API endpoints."""

import json

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import SuppressRequestLogsMixin, TestDataMixin
from the_flip.apps.wiki.actions import sync_template_option_index
from the_flip.apps.wiki.models import WikiPage

_page_counter = 0


def _make_content(name="test"):
    return (
        f'<!-- template:start name="{name}" -->\n'
        f"- [ ] step one\n"
        f'<!-- template:end name="{name}" -->\n'
    )


def _make_action(name="test", action="option", record_type="problem", label="Go", **extra):
    attrs = [
        f'name="{name}"',
        f'action="{action}"',
        f'type="{record_type}"',
        f'label="{label}"',
    ]
    for key in ("machine", "location", "priority", "tags", "title"):
        if key in extra:
            attrs.append(f'{key}="{extra[key]}"')
    return "<!-- template:action " + " ".join(attrs) + " -->"


def _make_template(name="test", action="option", record_type="problem", label="Go", **extra):
    return _make_content(name) + _make_action(name, action, record_type, label, **extra)


def _make_page(title=None, content=""):
    global _page_counter
    _page_counter += 1
    if title is None:
        title = f"API Page {_page_counter}"
    slug = title.lower().replace(" ", "-")
    # post_save signal auto-creates untagged WikiPageTag
    return WikiPage.objects.create(title=title, slug=slug, content=content)


@tag("views")
class WikiTemplateListViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for GET /api/wiki/templates/."""

    url = reverse("api-wiki-template-list")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.maintainer_user)

    def test_requires_auth(self):
        """Unauthenticated requests are redirected to login."""
        response = self.client_class().get(self.url, {"record_type": "problem"})
        self.assertEqual(response.status_code, 302)

    def test_record_type_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    def test_filters_by_record_type(self):
        page = _make_page(
            content=(
                _make_template("prob", record_type="problem", label="Problem Template")
                + "\n"
                + _make_template("log", record_type="log", label="Log Template")
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "problem"})
        data = json.loads(response.content)
        self.assertEqual(len(data["templates"]), 1)
        self.assertEqual(data["templates"][0]["label"], "Problem Template")

    def test_filters_by_priority(self):
        page = _make_page(
            content=(
                _make_template("task", record_type="problem", priority="task", label="Task Only")
                + "\n"
                + _make_template("any", record_type="problem", label="Any Priority")
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "problem", "priority": "task"})
        data = json.loads(response.content)
        labels = {t["label"] for t in data["templates"]}
        self.assertEqual(labels, {"Task Only", "Any Priority"})

    def test_priority_filter_excludes_other_priorities(self):
        page = _make_page(
            content=_make_template(
                "task", record_type="problem", priority="task", label="Task Only"
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "problem", "priority": "major"})
        data = json.loads(response.content)
        self.assertEqual(len(data["templates"]), 0)

    def test_filters_by_machine_slug(self):
        page = _make_page(
            content=(
                _make_template(
                    "machine-specific", record_type="log", machine="blackout", label="Blackout"
                )
                + "\n"
                + _make_template("any-machine", record_type="log", label="Any Machine")
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "log", "machine_slug": "blackout"})
        data = json.loads(response.content)
        labels = {t["label"] for t in data["templates"]}
        self.assertEqual(labels, {"Blackout", "Any Machine"})

    def test_no_machine_slug_excludes_machine_specific(self):
        page = _make_page(
            content=_make_template(
                "machine-specific", record_type="log", machine="blackout", label="Blackout"
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "log"})
        data = json.loads(response.content)
        self.assertEqual(len(data["templates"]), 0)

    def test_filters_by_location_slug(self):
        page = _make_page(
            content=(
                _make_template(
                    "loc-specific", record_type="log", location="floor-1", label="Floor 1"
                )
                + "\n"
                + _make_template("any-loc", record_type="log", label="Any Location")
            )
        )
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "log", "location_slug": "floor-1"})
        data = json.loads(response.content)
        labels = {t["label"] for t in data["templates"]}
        self.assertEqual(labels, {"Floor 1", "Any Location"})

    def test_empty_list_when_no_matches(self):
        response = self.client.get(self.url, {"record_type": "problem"})
        data = json.loads(response.content)
        self.assertEqual(data["templates"], [])

    def test_response_includes_content_url(self):
        page = _make_page(content=_make_template("intake", label="Intake"))
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "problem"})
        data = json.loads(response.content)
        expected_url = reverse(
            "api-wiki-template-content",
            kwargs={"page_pk": page.pk, "template_name": "intake"},
        )
        self.assertEqual(data["templates"][0]["content_url"], expected_url)

    def test_response_includes_page_title(self):
        page = _make_page(title="My Wiki Page", content=_make_template("intake", label="Intake"))
        sync_template_option_index(page)

        response = self.client.get(self.url, {"record_type": "problem"})
        data = json.loads(response.content)
        self.assertEqual(data["templates"][0]["page_title"], "My Wiki Page")


@tag("views")
class WikiTemplateContentViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for GET /api/wiki/templates/<page_pk>/<template_name>/content/."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.maintainer_user)

    def _url(self, page_pk, template_name):
        return reverse(
            "api-wiki-template-content",
            kwargs={"page_pk": page_pk, "template_name": template_name},
        )

    def test_requires_auth(self):
        """Unauthenticated requests are redirected to login."""
        page = _make_page(content=_make_template("intake"))
        response = self.client_class().get(self._url(page.pk, "intake"))
        self.assertEqual(response.status_code, 302)

    def test_returns_content(self):
        page = _make_page(content=_make_template("intake", label="Intake"))
        response = self.client.get(self._url(page.pk, "intake"))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("- [ ] step one", data["content"])

    def test_returns_tags_for_page_type(self):
        page = _make_page(
            content=_make_template(
                "intake",
                record_type="page",
                tags="guides,howto",
                title="New Guide",
                label="Guide",
            )
        )
        response = self.client.get(self._url(page.pk, "intake"))

        data = json.loads(response.content)
        self.assertEqual(data["tags"], ["guides", "howto"])
        self.assertEqual(data["title"], "New Guide")

    def test_no_tags_or_title_for_non_page_type(self):
        page = _make_page(content=_make_template("intake", record_type="problem"))
        response = self.client.get(self._url(page.pk, "intake"))

        data = json.loads(response.content)
        self.assertNotIn("tags", data)
        self.assertNotIn("title", data)

    def test_returns_priority_when_set(self):
        page = _make_page(content=_make_template("intake", record_type="problem", priority="task"))
        response = self.client.get(self._url(page.pk, "intake"))

        data = json.loads(response.content)
        self.assertEqual(data["priority"], "task")

    def test_404_for_missing_template(self):
        page = _make_page(content="No templates here.")
        response = self.client.get(self._url(page.pk, "nonexistent"))
        self.assertEqual(response.status_code, 404)

    def test_404_for_missing_page(self):
        response = self.client.get(self._url(99999, "intake"))
        self.assertEqual(response.status_code, 404)
