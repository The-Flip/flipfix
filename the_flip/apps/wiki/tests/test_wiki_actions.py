"""Tests for wiki action blocks: parsing, rendering, and pre-fill flow."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.actions import (
    ActionBlock,
    _validate_markers,
    build_action_url,
    build_create_url,
    extract_action_content,
    inject_buttons,
    prepare_for_rendering,
)
from the_flip.apps.wiki.models import WikiPage, WikiPageTag
from the_flip.apps.wiki.views import _resolve_action_tags


def _make_content(name="test"):
    """Create action:start/end content block (structural only, no action attrs)."""
    return (
        f'<!-- action:start name="{name}" -->\n'
        f"## {name.title()} Checklist\n\n"
        f"- [ ] step one\n"
        f"- [ ] step two\n"
        f'<!-- action:end name="{name}" -->\n'
    )


def _make_button(name="test", record_type="problem", machine="blackout", label="Go", **extra):
    """Create action:button marker with all action attributes."""
    machine_attr = f' machine="{machine}"' if machine else ""
    extra_attrs = "".join(f' {k}="{v}"' for k, v in extra.items() if v)
    return (
        f'<!-- action:button name="{name}" type="{record_type}"'
        f'{machine_attr}{extra_attrs} label="{label}" -->'
    )


def _make_action(name="test", record_type="problem", machine="blackout", label="Go"):
    """Create a complete action: content block + button."""
    return _make_content(name) + _make_button(name, record_type, machine, label)


# ---------------------------------------------------------------------------
# Structural validation tests (start/end markers only)
# ---------------------------------------------------------------------------


@tag("views")
class ValidateMarkersTests(TestCase):
    """Tests for _validate_markers (structural validation of start/end pairs)."""

    def test_no_markers_returns_empty_list(self):
        result = _validate_markers("Just plain markdown content.")
        self.assertEqual(result, [])

    def test_single_valid_block(self):
        content = _make_content("intake")
        result = _validate_markers(content)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "intake")

    def test_content_extracted_between_markers(self):
        content = _make_content("intake")
        result = _validate_markers(content)
        self.assertIn("step one", result[0].content)
        self.assertIn("step two", result[0].content)

    def test_multiple_blocks(self):
        content = _make_content("a") + _make_content("b") + _make_content("c")
        result = _validate_markers(content)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        names = {b.name for b in result}
        self.assertEqual(names, {"a", "b", "c"})

    # --- Structural error cases (returns None) ---

    def test_duplicate_names_returns_none(self):
        content = (
            '<!-- action:start name="dup" -->\n'
            "content\n"
            '<!-- action:end name="dup" -->\n'
            '<!-- action:start name="dup" -->\n'
            "more\n"
            '<!-- action:end name="dup" -->\n'
        )
        self.assertIsNone(_validate_markers(content))

    def test_nested_blocks_returns_none(self):
        content = (
            '<!-- action:start name="outer" -->\n'
            '<!-- action:start name="inner" -->\n'
            "content\n"
            '<!-- action:end name="inner" -->\n'
            '<!-- action:end name="outer" -->\n'
        )
        self.assertIsNone(_validate_markers(content))

    def test_unmatched_end_returns_none(self):
        content = '<!-- action:end name="orphan" -->\n'
        self.assertIsNone(_validate_markers(content))

    def test_unclosed_start_returns_none(self):
        content = '<!-- action:start name="x" -->\ncontent\n'
        self.assertIsNone(_validate_markers(content))

    def test_mismatched_names_returns_none(self):
        content = '<!-- action:start name="a" -->\ncontent\n<!-- action:end name="b" -->\n'
        self.assertIsNone(_validate_markers(content))


# ---------------------------------------------------------------------------
# Token substitution tests
# ---------------------------------------------------------------------------


@tag("views")
class PrepareForRenderingTests(TestCase):
    """Tests for prepare_for_rendering (token substitution)."""

    def test_no_markers_returns_content_unchanged(self):
        content = "Just plain text."
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(processed, content)
        self.assertEqual(tokens, {})

    def test_markers_stripped_content_preserved(self):
        content = _make_action("intake") + "\nSome other text.\n"
        processed, _tokens = prepare_for_rendering(content)
        self.assertNotIn("action:start", processed)
        self.assertNotIn("action:end", processed)
        self.assertIn("step one", processed)
        self.assertIn("Some other text.", processed)

    def test_button_replaced_with_token(self):
        content = _make_action("intake")
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("action:button", processed)
        self.assertEqual(len(tokens), 1)
        the_token = next(iter(tokens))
        self.assertIn(the_token, processed)

    def test_multiple_buttons_for_same_block(self):
        content = _make_content("intake") + _make_button("intake") + "\n" + _make_button("intake")
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 2)
        for t in tokens:
            self.assertIn(t, processed)

    def test_orphan_button_silently_removed(self):
        content = _make_content("a") + _make_button("nonexistent")
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("action:button", processed)
        for block in tokens.values():
            self.assertNotEqual(block.name, "nonexistent")

    def test_structural_error_returns_original(self):
        content = (
            '<!-- action:start name="outer" -->\n'
            '<!-- action:start name="inner" -->\n'
            "content\n"
            '<!-- action:end name="inner" -->\n'
            '<!-- action:end name="outer" -->\n' + _make_button("outer") + "\n"
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertIn("action:start", processed)

    def test_orphan_buttons_cleaned_when_no_blocks(self):
        content = "Some text\n" + _make_button("missing") + "\nmore text"
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("action:button", processed)
        self.assertEqual(tokens, {})

    def test_button_with_invalid_type_skipped(self):
        content = _make_content("x") + '<!-- action:button name="x" type="invalid" label="Go" -->'
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertNotIn("action:button", processed)

    def test_button_missing_type_skipped(self):
        content = _make_content("x") + '<!-- action:button name="x" label="Go" -->'
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_button_missing_label_skipped(self):
        content = _make_content("x") + '<!-- action:button name="x" type="problem" -->'
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_button_invalid_priority_skipped(self):
        content = _make_content("x") + _make_button("x", priority="banana")
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertNotIn("action:button", processed)

    def test_button_attrs_populate_action_block(self):
        content = _make_content("intake") + _make_button("intake", "log", "blackout", "Start Log")
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.name, "intake")
        self.assertEqual(block.record_type, "log")
        self.assertEqual(block.machine_slug, "blackout")
        self.assertEqual(block.label, "Start Log")
        self.assertIn("step one", block.content)

    def test_button_optional_machine(self):
        content = _make_content("x") + _make_button("x", machine="")
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.machine_slug, "")

    def test_page_type_accepted(self):
        content = _make_content("x") + _make_button("x", record_type="page", machine="")
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.record_type, "page")

    def test_button_tags_populated(self):
        content = _make_content("x") + _make_button(
            "x", record_type="page", machine="", tags="guides,archive"
        )
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.tags, "guides,archive")

    def test_button_title_populated(self):
        content = _make_content("x") + _make_button(
            "x", record_type="page", machine="", title="My Title"
        )
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.title, "My Title")

    def test_button_priority_populated(self):
        content = _make_content("x") + _make_button("x", priority="task")
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.priority, "task")

    def test_button_priority_defaults_to_empty(self):
        content = _make_content("x") + _make_button("x")
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.priority, "")


# ---------------------------------------------------------------------------
# Button injection tests
# ---------------------------------------------------------------------------


@tag("views")
class InjectButtonsTests(TestCase):
    """Tests for inject_buttons (post-sanitization HTML injection)."""

    def test_token_replaced_with_button_html(self):
        block = ActionBlock("intake", "problem", "blackout", "Start Intake", "content")
        placeholder = "abc123"
        html = f"<p>Before</p>{placeholder}<p>After</p>"
        result = inject_buttons(html, {placeholder: block}, page_pk=42)
        self.assertIn("wiki-action", result)
        self.assertIn("Start Intake", result)
        self.assertIn('class="btn btn--secondary"', result)
        self.assertNotIn(placeholder, result)

    def test_button_url_points_to_prefill_endpoint(self):
        block = ActionBlock("intake", "problem", "blackout", "Start Intake", "content")
        placeholder = "abc123"
        html = f"{placeholder}"
        result = inject_buttons(html, {placeholder: block}, page_pk=42)
        expected_url = reverse(
            "wiki-action-prefill", kwargs={"page_pk": 42, "action_name": "intake"}
        )
        self.assertIn(expected_url, result)

    def test_label_html_escaped(self):
        block = ActionBlock("x", "problem", "", '<script>alert("xss")</script>', "")
        placeholder = "placeholder1"
        result = inject_buttons(placeholder, {placeholder: block}, page_pk=1)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)


# ---------------------------------------------------------------------------
# URL construction tests
# ---------------------------------------------------------------------------


@tag("views")
class URLConstructionTests(TestCase):
    """Tests for build_action_url and build_create_url."""

    def test_build_action_url(self):
        block = ActionBlock("intake", "problem", "blackout", "Go", "")
        url = build_action_url(block, page_pk=42)
        self.assertEqual(
            url, reverse("wiki-action-prefill", kwargs={"page_pk": 42, "action_name": "intake"})
        )

    def test_build_create_url_problem_with_machine(self):
        block = ActionBlock("x", "problem", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(
            url, reverse("problem-report-create-machine", kwargs={"slug": "test-machine"})
        )

    def test_build_create_url_problem_global(self):
        block = ActionBlock("x", "problem", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("problem-report-create"))

    def test_build_create_url_log_with_machine(self):
        block = ActionBlock("x", "log", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("log-create-machine", kwargs={"slug": "test-machine"}))

    def test_build_create_url_log_global(self):
        block = ActionBlock("x", "log", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("log-create-global"))

    def test_build_create_url_partrequest_with_machine(self):
        block = ActionBlock("x", "partrequest", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(
            url, reverse("part-request-create-machine", kwargs={"slug": "test-machine"})
        )

    def test_build_create_url_partrequest_global(self):
        block = ActionBlock("x", "partrequest", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("part-request-create"))

    def test_build_create_url_page_global(self):
        block = ActionBlock("x", "page", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("wiki-page-create"))

    def test_build_create_url_page_ignores_machine_slug(self):
        block = ActionBlock("x", "page", "some-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("wiki-page-create"))


# ---------------------------------------------------------------------------
# Content extraction tests
# ---------------------------------------------------------------------------


@tag("views")
class ExtractActionContentTests(TestCase):
    """Tests for extract_action_content."""

    def test_extract_existing_block(self):
        content = _make_action("intake", "problem")
        block = extract_action_content(content, "intake")
        self.assertIsNotNone(block)
        self.assertEqual(block.name, "intake")
        self.assertEqual(block.record_type, "problem")
        self.assertIn("step one", block.content)

    def test_extract_nonexistent_returns_none(self):
        content = _make_action("intake")
        self.assertIsNone(extract_action_content(content, "missing"))

    def test_extract_correct_block_from_multiple(self):
        content = _make_action("a", "problem") + _make_action("b", "log")
        block = extract_action_content(content, "b")
        self.assertIsNotNone(block)
        self.assertEqual(block.record_type, "log")

    def test_extract_returns_none_on_structural_error(self):
        content = (
            '<!-- action:start name="outer" -->\n'
            '<!-- action:start name="inner" -->\n'
            "content\n"
            '<!-- action:end name="inner" -->\n'
            '<!-- action:end name="outer" -->\n'
        )
        self.assertIsNone(extract_action_content(content, "outer"))

    def test_extract_returns_none_without_button(self):
        """Content block exists but no button marker → None."""
        content = _make_content("intake")
        self.assertIsNone(extract_action_content(content, "intake"))

    def test_extract_returns_none_with_invalid_button(self):
        """Content block exists but button has invalid type → None."""
        content = _make_content("x") + '<!-- action:button name="x" type="invalid" label="Go" -->'
        self.assertIsNone(extract_action_content(content, "x"))

    def test_extract_returns_none_with_invalid_priority(self):
        content = _make_content("x") + _make_button("x", priority="banana")
        self.assertIsNone(extract_action_content(content, "x"))

    def test_extract_page_type_with_tags_and_title(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", tags="@source", title="Evaluation"
        )
        block = extract_action_content(content, "eval")
        self.assertIsNotNone(block)
        self.assertEqual(block.record_type, "page")
        self.assertEqual(block.tags, "@source")
        self.assertEqual(block.title, "Evaluation")

    def test_extract_problem_type_with_priority(self):
        content = _make_content("x") + _make_button("x", priority="task")
        block = extract_action_content(content, "x")
        self.assertIsNotNone(block)
        self.assertEqual(block.priority, "task")


# ---------------------------------------------------------------------------
# _resolve_action_tags tests (DB-aware)
# ---------------------------------------------------------------------------


@tag("views")
class ResolveActionTagsTests(TestDataMixin, TestCase):
    """Tests for _resolve_action_tags."""

    def _create_page_with_tags(self, *tags):
        page = WikiPage.objects.create(title="Template", slug="template", content="")
        for t in tags:
            WikiPageTag.objects.create(page=page, tag=t, slug="template")
        return page

    def test_explicit_tag(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_action_tags("evaluations", page)
        self.assertEqual(result, ["evaluations"])

    def test_multiple_explicit_tags(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_action_tags("evaluations,archive", page)
        self.assertEqual(result, ["evaluations", "archive"])

    def test_source_expands_to_page_tags(self):
        page = self._create_page_with_tags("guides", "templates")
        result = _resolve_action_tags("@source", page)
        self.assertIn("guides", result)
        self.assertIn("templates", result)

    def test_source_excludes_untagged_sentinel(self):
        # WikiPage post_save signal auto-creates the untagged sentinel tag,
        # so a page with no explicit tags already has only the sentinel.
        page = WikiPage.objects.create(title="Untagged", slug="untagged", content="")
        result = _resolve_action_tags("@source", page)
        self.assertEqual(result, [])

    def test_mixed_source_and_explicit(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_action_tags("@source,archive", page)
        self.assertEqual(result, ["guides", "archive"])

    def test_deduplicates_preserving_order(self):
        page = self._create_page_with_tags("evaluations")
        result = _resolve_action_tags("@source,evaluations,extra", page)
        self.assertEqual(result, ["evaluations", "extra"])

    def test_empty_string_returns_empty(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_action_tags("", page)
        self.assertEqual(result, [])

    def test_whitespace_stripped(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_action_tags("  evaluations , archive  ", page)
        self.assertEqual(result, ["evaluations", "archive"])


# ---------------------------------------------------------------------------
# Integration: rendering (template tag)
# ---------------------------------------------------------------------------


@tag("views")
class WikiContentRenderingTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests: wiki page renders action buttons correctly."""

    def _create_page(self, content):
        page = WikiPage.objects.create(title="Test Page", slug="test-page", content=content)
        WikiPageTag.objects.create(page=page, tag="docs", slug="test-page")
        return page

    def _get_page_html(self, path="docs/test-page"):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("wiki-page-detail", args=[path]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_page_without_actions_renders_normally(self):
        self._create_page("Just some **bold** text.")
        html = self._get_page_html()
        self.assertIn("<strong>bold</strong>", html)
        self.assertNotIn("wiki-action", html)

    def test_action_content_renders_as_markdown(self):
        self._create_page(_make_action("intake"))
        html = self._get_page_html()
        self.assertIn("step one", html)
        self.assertIn("task-list-item", html)

    def test_button_renders_in_output(self):
        self._create_page(_make_action("intake"))
        html = self._get_page_html()
        self.assertIn("wiki-action", html)
        self.assertIn("Go", html)
        self.assertIn("btn btn--secondary", html)

    def test_button_links_to_prefill_endpoint(self):
        page = self._create_page(_make_action("intake"))
        html = self._get_page_html()
        expected_url = reverse(
            "wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "intake"}
        )
        self.assertIn(expected_url, html)

    def test_multiple_buttons_render(self):
        content = (
            _make_content("a")
            + _make_content("b")
            + _make_button("a", "problem", "test-machine", "Report Problem")
            + _make_button("b", "log", "test-machine", "Log Entry")
        )
        self._create_page(content)
        html = self._get_page_html()
        self.assertIn("Report Problem", html)
        self.assertIn("Log Entry", html)

    def test_markers_not_visible_in_output(self):
        self._create_page(_make_action("intake"))
        html = self._get_page_html()
        # Check the rendered content area only (not the hidden textarea
        # which contains raw markdown for checkbox toggle JS).
        display_html = html.split("data-text-display")[1].split("data-text-textarea")[0]
        self.assertNotIn("action:start", display_html)
        self.assertNotIn("action:end", display_html)
        self.assertNotIn("action:button", display_html)

    def test_malformed_markers_degrade_gracefully(self):
        content = '<!-- action:start name="x" -->\ncontent\n'
        self._create_page(content)
        html = self._get_page_html()
        self.assertNotIn("wiki-action", html)
        self.assertIn("content", html)


# ---------------------------------------------------------------------------
# Integration: prefill view
# ---------------------------------------------------------------------------


@tag("views")
class WikiActionPrefillViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests for WikiActionPrefillView."""

    def _create_page(self, content):
        return WikiPage.objects.create(title="Test Page", slug="test-page", content=content)

    def test_redirects_to_problem_create(self):
        page = self._create_page(_make_action("intake", "problem", "test-machine", "Go"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "intake"})
        response = self.client.get(url)
        expected = reverse("problem-report-create-machine", kwargs={"slug": "test-machine"})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_redirects_to_log_create(self):
        page = self._create_page(_make_action("x", "log", "test-machine", "Go"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        response = self.client.get(url)
        expected = reverse("log-create-machine", kwargs={"slug": "test-machine"})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_redirects_to_partrequest_create(self):
        page = self._create_page(_make_action("x", "partrequest", "", "Go"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        response = self.client.get(url)
        expected = reverse("part-request-create")
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_stores_correct_field_in_session(self):
        page = self._create_page(_make_action("intake", "problem"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "intake"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertIsNotNone(prefill)
        self.assertEqual(prefill["field"], "description")
        self.assertIn("step one", prefill["content"])

    def test_log_type_uses_text_field(self):
        page = self._create_page(_make_action("x", "log"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        self.client.get(url)
        self.assertEqual(self.client.session["form_prefill"]["field"], "text")

    def test_partrequest_type_uses_text_field(self):
        page = self._create_page(_make_action("x", "partrequest"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        self.client.get(url)
        self.assertEqual(self.client.session["form_prefill"]["field"], "text")

    def test_missing_page_returns_404(self):
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": 99999, "action_name": "x"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_missing_action_returns_404(self):
        page = self._create_page(_make_action("intake"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "missing"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        page = self._create_page(_make_action("intake"))
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "intake"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_page_type_redirects_to_wiki_create(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        response = self.client.get(url)
        self.assertRedirects(response, reverse("wiki-page-create"), fetch_redirect_response=False)

    def test_page_type_stores_content_field(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertEqual(prefill["field"], "content")
        self.assertIn("step one", prefill["content"])

    def test_page_type_stores_tags_in_session(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", tags="guides", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        self.assertEqual(self.client.session.get("form_prefill_tags"), ["guides"])

    def test_page_type_stores_title_in_session(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", title="Evaluation", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        self.assertEqual(self.client.session.get("form_prefill_title"), "Evaluation")

    def test_page_type_resolves_source_tags(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", tags="@source", label="Go"
        )
        page = self._create_page(content)
        WikiPageTag.objects.create(page=page, tag="templates", slug="test-page")
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        # _create_page doesn't add tags, but we added "templates" above
        self.assertIn("templates", self.client.session.get("form_prefill_tags", []))

    def test_page_type_no_tags_omits_session_key(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        self.assertNotIn("form_prefill_tags", self.client.session)

    def test_page_type_no_title_omits_session_key(self):
        content = _make_content("eval") + _make_button(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "eval"})
        self.client.get(url)
        self.assertNotIn("form_prefill_title", self.client.session)

    def test_priority_stored_in_session_extra_initial(self):
        page = self._create_page(_make_content("x") + _make_button("x", priority="task"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertEqual(prefill["extra_initial"], {"priority": "task"})

    def test_no_priority_omits_extra_initial(self):
        page = self._create_page(_make_action("x"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-action-prefill", kwargs={"page_pk": page.pk, "action_name": "x"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertNotIn("extra_initial", prefill)


# ---------------------------------------------------------------------------
# Integration: FormPrefillMixin
# ---------------------------------------------------------------------------


@tag("views")
class FormPrefillMixinTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests for FormPrefillMixin via actual create views."""

    def test_problem_report_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "description", "content": "Pre-filled text"}
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertContains(response, "Pre-filled text")

    def test_extra_initial_prefills_priority(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {
            "field": "description",
            "content": "Task text",
            "extra_initial": {"priority": "task"},
        }
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertContains(response, "Task text")
        # Priority "task" should be pre-selected in the dropdown
        self.assertContains(response, '<option value="task" selected')

    def test_log_entry_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "text", "content": "Log content here"}
        session.save()
        response = self.client.get(reverse("log-create-global"))
        self.assertContains(response, "Log content here")

    def test_part_request_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "text", "content": "Part request text"}
        session.save()
        response = self.client.get(reverse("part-request-create"))
        self.assertContains(response, "Part request text")

    def test_session_cleared_after_prefill(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "description", "content": "one-shot"}
        session.save()
        self.client.get(reverse("problem-report-create"))
        self.assertNotIn("form_prefill", self.client.session)

    def test_no_session_data_form_unchanged(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("problem-report-create"))
        self.assertEqual(response.status_code, 200)

    def test_wiki_page_content_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "content", "content": "- [ ] checklist item"}
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        self.assertContains(response, "- [ ] checklist item")

    def test_wiki_page_title_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill_title"] = "Evaluation Checklist"
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        self.assertContains(response, "Evaluation Checklist")

    def test_wiki_page_tags_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill_tags"] = ["guides", "evaluations"]
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        # Tags render in the tag chip component's data attribute and hidden inputs
        self.assertContains(response, 'data-initial-tags="guides, evaluations"')
        self.assertContains(response, 'name="tags" value="guides"')
        self.assertContains(response, 'name="tags" value="evaluations"')

    def test_wiki_page_session_cleared_after_prefill(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "content", "content": "template"}
        session["form_prefill_tags"] = ["guides"]
        session["form_prefill_title"] = "Title"
        session.save()
        self.client.get(reverse("wiki-page-create"))
        self.assertNotIn("form_prefill", self.client.session)
        self.assertNotIn("form_prefill_tags", self.client.session)
        self.assertNotIn("form_prefill_title", self.client.session)
