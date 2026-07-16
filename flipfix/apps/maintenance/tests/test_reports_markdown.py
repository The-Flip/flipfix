"""Tests for the daily-report markdown renderers."""

from __future__ import annotations

from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
    create_location,
    create_machine,
    create_machine_model,
)
from flipfix.apps.maintenance.reports import (
    build_report,
    render_markdown,
    render_verbose_text,
)

S = MachineInstance.OperationalStatus
Z = Location.Zone


@tag("models")
class MarkdownTests(TestCase):
    def setUp(self):
        self.front = create_location("Coin-Op", Z.FRONT)
        self.workshop = create_location("Workshop", Z.WORKSHOP)
        self.now = timezone.now()

    def _report(self):
        return build_report(self.now)

    def test_digest_stays_within_discord_content_limit(self):
        # A busy museum: many machines per zone. The digest is bounded (emoji
        # rows + capped-5 lists), so it must fit Discord's 2000-char content cap.
        for i in range(40):
            create_machine(
                location=self.front,
                operational_status=S.BROKEN,
                model=create_machine_model(year=1980 + i),
            )
        md = render_markdown(self._report(), link_url="https://x/report")
        self.assertLess(len(md), 2000)

    def test_backtick_rows_and_titles_present(self):
        create_machine(location=self.front, model=create_machine_model())
        md = render_markdown(self._report())
        self.assertIn("**Front of House:**", md)
        self.assertIn("`COIN-OP", md)  # monospace zone row

    def test_includes_link_when_url_given(self):
        md = render_markdown(self._report(), link_url="https://flip/report")
        self.assertIn("https://flip/report", md)

    def test_link_wrapped_in_angle_brackets_to_suppress_embed(self):
        # Discord renders a bare URL as a preview card; angle brackets suppress it.
        md = render_markdown(self._report(), link_url="https://flip/report")
        self.assertIn("<https://flip/report>", md)

    def test_omits_link_when_no_url(self):
        md = render_markdown(self._report())
        self.assertNotIn("🔗", md)

    def test_legend_present(self):
        md = render_markdown(self._report())
        self.assertIn("😀 good", md)
        self.assertIn("😭 down", md)
        self.assertIn("😶 unknown", md)  # face with no mouth

    def test_verbose_lists_every_machine_with_inputs(self):
        create_machine(
            location=self.workshop,
            operational_status=S.BROKEN,
            name="Gorgar",
            model=create_machine_model(year=1979),
        )
        text = render_verbose_text(self._report())
        self.assertIn("Gorgar (1979)", text)
        self.assertIn("status=broken", text)
        self.assertIn("→ down", text)
