"""Unit tests for the mobile parity resolver.

These exercise the pure half of the audit — CSS parsing, HTML tree building,
accessible names, affordance keys and viewport visibility — against synthetic
input. They need no database and no application templates, so they keep passing
while the real templates are being fixed, which is exactly where the confidence
in this tool has to come from.
"""

from __future__ import annotations

from django.test import SimpleTestCase, tag

from flipfix.apps.core.mobile_parity.affordances import accessible_name, extract
from flipfix.apps.core.mobile_parity.css_rules import (
    UnsupportedCssError,
    load_display_index,
    parse_display_index,
)
from flipfix.apps.core.mobile_parity.dom import MalformedHtmlError, parse_document
from flipfix.apps.core.mobile_parity.visibility import concealment, is_visible


def _keys(html: str) -> set[str]:
    return {affordance.key for _, affordance in extract(parse_document(html))}


@tag("unit")
class DisplayIndexTests(SimpleTestCase):
    """Resolving a display value for a set of classes at a width."""

    def test_min_width_rule_applies_only_above_its_breakpoint(self):
        index = parse_display_index(
            ".panel { display: none; } @media (min-width: 1024px) { .panel { display: block; } }"
        )
        classes = frozenset({"panel"})
        self.assertEqual(index.display_for(classes, 390), "none")
        self.assertEqual(index.display_for(classes, 1280), "block")

    def test_later_rule_wins_at_equal_specificity(self):
        index = parse_display_index(".a { display: flex; } .a { display: none; }")
        self.assertEqual(index.display_for(frozenset({"a"}), 390), "none")

    def test_important_beats_a_later_plain_rule(self):
        index = parse_display_index(".a { display: none !important; } .a { display: flex; }")
        self.assertEqual(index.display_for(frozenset({"a"}), 390), "none")

    def test_display_resolves_across_all_classes_on_the_element(self):
        """A modifier defined later overrides the base class it sits beside."""
        index = parse_display_index(
            ".nav { display: flex; } @media (min-width: 768px) { .nav--mobile { display: none; } }"
        )
        classes = frozenset({"nav", "nav--mobile"})
        self.assertEqual(index.display_for(classes, 390), "flex")
        self.assertEqual(index.display_for(classes, 1280), "none")

    def test_unstyled_classes_resolve_to_none_of_our_business(self):
        index = parse_display_index(".a { display: none; }")
        self.assertIsNone(index.display_for(frozenset({"unrelated"}), 390))

    def test_toggle_classes_are_those_that_change_with_width(self):
        index = parse_display_index(
            ".fixed { display: flex; }"
            ".swaps { display: none; }"
            "@media (min-width: 640px) { .swaps { display: block; } }"
        )
        self.assertEqual(index.toggle_classes(), frozenset({"swaps"}))

    def test_revealed_at_reports_the_narrowest_visible_width(self):
        index = parse_display_index(
            ".swaps { display: none; } @media (min-width: 640px) { .swaps { display: block; } }"
        )
        self.assertEqual(index.revealed_at("swaps"), 640)

    def test_revealed_at_is_none_when_the_class_never_hides(self):
        index = parse_display_index(".shown { display: flex; }")
        self.assertIsNone(index.revealed_at("shown"))

    def test_declaration_without_trailing_semicolon_is_read(self):
        index = parse_display_index(".a { display: none }")
        self.assertEqual(index.display_for(frozenset({"a"}), 390), "none")

    def test_comments_do_not_shift_reported_line_numbers(self):
        index = parse_display_index("/* a\nmulti-line\ncomment */\n.a { display: none; }")
        self.assertEqual(index.rules[0].line, 4)


@tag("unit")
class UnsupportedCssTests(SimpleTestCase):
    """The parser refuses to guess, so unmodelled CSS breaks the build loudly."""

    def test_max_width_query_is_rejected(self):
        """A max-width query inverts the mobile-first model the resolver assumes."""
        with self.assertRaisesMessage(UnsupportedCssError, "max-width"):
            parse_display_index("@media (max-width: 640px) { .a { display: none; } }")

    def test_display_inside_an_unmodelled_at_rule_is_rejected(self):
        with self.assertRaises(UnsupportedCssError):
            parse_display_index("@media (prefers-color-scheme: dark) { .a { display: none; } }")

    def test_unmodelled_at_rule_without_display_is_tolerated(self):
        index = parse_display_index(
            "@media (prefers-color-scheme: dark) { .a { color: red; } } .b { display: none; }"
        )
        self.assertEqual(index.display_for(frozenset({"b"}), 390), "none")

    def test_compound_selector_on_a_toggle_class_is_rejected(self):
        """Such a rule out-specifies the flat model and would be mis-ranked."""
        with self.assertRaisesMessage(UnsupportedCssError, "flat specificity"):
            parse_display_index(
                ".panel { display: none; }"
                "@media (min-width: 1024px) { .panel { display: block; } }"
                ".wrapper .panel { display: block; }"
            )

    def test_compound_selector_on_a_stable_class_is_tolerated(self):
        """Only toggle classes matter: everything else resolves the same at both widths."""
        index = parse_display_index(".wrapper > .item { display: flex; } .a { display: none; }")
        self.assertEqual(index.display_for(frozenset({"a"}), 390), "none")

    def test_nested_style_rules_are_rejected(self):
        with self.assertRaisesMessage(UnsupportedCssError, "nested style rule"):
            parse_display_index(".outer { color: red; .inner { display: none; } }")


@tag("unit")
class DocumentTreeTests(SimpleTestCase):
    """Ancestor chains decide visibility, so the tree has to be trustworthy."""

    def test_void_elements_do_not_swallow_their_siblings(self):
        root = parse_document("<div><input name='a'><span>after</span></div>")
        div = root.children[0]
        self.assertEqual([child.tag for child in div.children], ["input", "span"])

    def test_repeated_list_items_close_implicitly(self):
        root = parse_document("<ul><li>one<li>two</ul>")
        self.assertEqual(len(root.children[0].children), 2)

    def test_stray_closing_tag_is_rejected(self):
        with self.assertRaises(MalformedHtmlError):
            parse_document("<div>text</span></div>")

    def test_unclosed_element_is_rejected(self):
        with self.assertRaises(MalformedHtmlError):
            parse_document("<div><section>text</div>")

    def test_ancestors_run_from_self_to_root(self):
        root = parse_document("<div class='outer'><p class='inner'>hi</p></div>")
        paragraph = root.children[0].children[0]
        self.assertEqual([node.tag for node in paragraph.ancestors()], ["p", "div", "#document"])


@tag("unit")
class AccessibleNameTests(SimpleTestCase):
    """Naming follows the accessible name computation closely enough to be useful."""

    def test_icon_only_control_is_named_by_its_visually_hidden_span(self):
        """This is the shape ``{% icon "name" label="..." %}`` renders."""
        root = parse_document(
            '<a href="/wiki/reorder/">'
            '<i class="fa-solid fa-arrows" aria-hidden="true"></i>'
            '<span class="visually-hidden">Reorder Nav</span></a>'
        )
        self.assertEqual(accessible_name(root.children[0]), "Reorder Nav")

    def test_aria_label_takes_precedence_over_text(self):
        root = parse_document('<button aria-label="Close dialog">x</button>')
        self.assertEqual(accessible_name(root.children[0]), "Close dialog")

    def test_aria_hidden_subtrees_contribute_nothing(self):
        root = parse_document('<button><i aria-hidden="true">glyph</i></button>')
        self.assertEqual(accessible_name(root.children[0]), "")

    def test_placeholder_is_the_last_resort(self):
        root = parse_document('<input name="q" placeholder="Search docs">')
        self.assertEqual(accessible_name(root.children[0]), "Search docs")

    def test_aria_labelledby_resolves_within_the_document(self):
        root = parse_document('<h2 id="t">Machines</h2><a href="/" aria-labelledby="t">go</a>')
        self.assertEqual(accessible_name(root.children[1]), "Machines")


@tag("unit")
class AffordanceKeyTests(SimpleTestCase):
    """Keys identify what an affordance targets, never what it is called."""

    def test_link_keys_on_its_url_name_not_its_parameters(self):
        """Fixture slugs must not leak into keys, or baselines churn constantly."""
        first = _keys('<a href="/machines/one-machine/edit/">Edit</a>')
        second = _keys('<a href="/machines/another-machine/edit/">Edit</a>')
        self.assertEqual(first, second)
        self.assertEqual(first, {"link:machine-edit"})

    def test_link_key_ignores_a_changing_label(self):
        """The stylesheet swaps button copy by width; keys must not follow."""
        short = _keys('<a href="/wiki/"><span>Docs</span></a>')
        long = _keys('<a href="/wiki/"><span>Documentation</span></a>')
        self.assertEqual(short, long)

    def test_same_link_rendered_twice_collapses_to_one_key(self):
        html = '<div><a href="/wiki/">Docs</a></div><aside><a href="/wiki/">Docs</a></aside>'
        self.assertEqual(_keys(html), {"link:wiki-home"})

    def test_unresolvable_href_falls_back_to_its_path(self):
        self.assertEqual(_keys('<a href="/no/such/page/">X</a>'), {"link:/no/such/page/"})

    def test_external_link_is_keyed_by_host(self):
        keys = _keys('<a href="https://example.com/docs">Docs</a>')
        self.assertEqual(keys, {"link:external:example.com/docs"})

    def test_submit_button_is_keyed_by_the_form_it_posts(self):
        html = (
            '<form method="post" action="/wiki/create/"><button type="submit">Save</button></form>'
        )
        self.assertEqual(_keys(html), {"form:wiki-page-create:post"})

    def test_field_is_keyed_by_its_form_and_name(self):
        html = '<form method="get" action="/wiki/search/"><input name="q"></form>'
        self.assertEqual(_keys(html), {"field:form:wiki-search:get:q"})

    def test_hidden_inputs_are_not_affordances(self):
        html = '<form method="post" action="/wiki/create/"><input type="hidden" name="csrf"></form>'
        self.assertEqual(_keys(html), set())

    def test_disclosure_controls_are_not_affordances(self):
        """The menu it opens is enumerated separately; counting both invents gaps."""
        html = '<button aria-haspopup="true" aria-label="Account menu">A</button>'
        self.assertEqual(_keys(html), set())

    def test_headings_are_captured_as_content(self):
        self.assertEqual(_keys("<h2>Open Problems</h2>"), {"content:open-problems"})

    def test_content_keys_blur_out_values_that_move_with_fixtures(self):
        first = _keys("<h3>Logged 4 entries on 2026-01-02</h3>")
        second = _keys("<h3>Logged 97 entries on 2025-11-30</h3>")
        self.assertEqual(first, second)


@tag("unit")
class ViewportVisibilityTests(SimpleTestCase):
    """What counts as hidden, and what deliberately does not."""

    CSS = (
        ".sidebar { display: none; }"
        "@media (min-width: 1024px) { .sidebar { display: block; } }"
        ".hidden { display: none !important; }"
        ".visually-hidden { position: absolute; }"
    )

    def setUp(self):
        self.index = parse_display_index(self.CSS)

    def test_element_inside_a_hidden_ancestor_is_hidden(self):
        root = parse_document('<aside class="sidebar"><a href="/wiki/">Docs</a></aside>')
        link = root.children[0].children[0]
        self.assertFalse(is_visible(link, self.index, 390))
        self.assertTrue(is_visible(link, self.index, 1280))

    def test_concealment_names_the_class_and_the_element_carrying_it(self):
        root = parse_document('<aside class="sidebar"><a href="/wiki/">Docs</a></aside>')
        found = concealment(root.children[0].children[0], self.index, 390)
        self.assertIsNotNone(found)
        self.assertEqual(found.selector, ".sidebar")
        self.assertEqual(found.at_tag, "aside")

    def test_js_toggled_hidden_class_never_conceals(self):
        """``.hidden`` is dropdown open/closed state — its contents are one tap away."""
        root = parse_document('<div class="hidden"><a href="/wiki/">Docs</a></div>')
        link = root.children[0].children[0]
        self.assertTrue(is_visible(link, self.index, 390))
        self.assertTrue(is_visible(link, self.index, 1280))

    def test_screen_reader_text_is_not_treated_as_hidden(self):
        root = parse_document('<span class="visually-hidden">Reorder Nav</span>')
        self.assertTrue(is_visible(root.children[0], self.index, 390))


@tag("unit")
class ProjectStylesheetTests(SimpleTestCase):
    """The real stylesheet still matches the shape the resolver relies on."""

    def test_the_project_stylesheet_parses(self):
        index = load_display_index()
        self.assertTrue(index.rules)

    def test_breakpoints_match_the_documented_ladder(self):
        self.assertEqual(load_display_index().breakpoints, (420, 540, 640, 768, 900, 1024))

    def test_the_layout_sidebar_is_a_viewport_toggle(self):
        """If this stops being true, the audit's main finding class has moved."""
        index = load_display_index()
        self.assertIn("two-column__sidebar", index.toggle_classes())
        self.assertEqual(index.revealed_at("two-column__sidebar"), 1024)
