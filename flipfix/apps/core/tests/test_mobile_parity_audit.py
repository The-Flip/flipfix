"""The regression gate for mobile/desktop UI parity.

The site's page actions live in two hand-maintained places — ``mobile_actions``
and ``sidebar`` — and only CSS decides which one you see, so they drift. This
test renders every page at both viewports and holds the resulting gap list
against a committed baseline that is only ever allowed to shrink.

To see the findings themselves, run ``manage.py check_mobile_parity``.
See ``docs/MobileParity.md`` for the design and its blind spots.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase, tag

from flipfix.apps.core.mobile_parity import routes as parity_routes
from flipfix.apps.core.mobile_parity.audit import run_audit
from flipfix.apps.core.mobile_parity.baseline import diff_against, load_baseline
from flipfix.apps.core.mobile_parity.routes import UnmappedRouteError, static_exclusion
from flipfix.apps.core.routing import get_registered_routes
from flipfix.apps.core.test_utils import SuppressRequestLogsMixin

_REMEDY = "  python manage.py check_mobile_parity --update-baseline --accept-new"


@tag("views")
class MobileParityBaselineTests(SuppressRequestLogsMixin, TestCase):
    """The known parity gaps must never grow, and must never go stale."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # One full pass for the whole class: the audit renders every page as
        # every relevant persona, which is far too expensive to repeat per test.
        # The mixin keeps the deliberate 404s and 405s out of the log.
        cls.result = run_audit()
        cls.baseline = load_baseline()
        cls.diff = diff_against(cls.result, cls.baseline)

    def test_no_new_mobile_parity_gaps(self):
        """Nothing may become desktop-only without being recorded first."""
        if not self.diff.new:
            return
        listing = "\n".join(
            f"  {gap.route} [{gap.persona}] {gap.key}  <{gap.element}> {gap.label!r}\n"
            f"      hidden by {gap.hidden_by}, revealed at {gap.revealed_at}px"
            for gap in self.diff.new
        )
        self.fail(
            f"{len(self.diff.new)} affordance(s) are reachable on desktop but not on "
            f"mobile, and are not in the baseline:\n{listing}\n"
            f"Give each one a mobile counterpart, or record it:\n{_REMEDY}"
        )

    def test_baseline_contains_no_stale_entries(self):
        """A fixed gap must be removed from the baseline, so the list shrinks."""
        if not self.diff.stale:
            return
        listing = "\n".join(
            f"  {entry.route} [{entry.persona}] {entry.key}" for entry in self.diff.stale
        )
        self.fail(
            f"{len(self.diff.stale)} baseline entr(ies) no longer reproduce. If you fixed "
            f"them, delete them from the baseline so it keeps ratcheting down:\n{listing}\n"
            f"Or rewrite it:\n  python manage.py check_mobile_parity --update-baseline"
        )

    def test_every_registered_route_is_audited_or_explicitly_skipped(self):
        """A new page must be deliberately covered or deliberately excluded."""
        audited = {route for route, _ in self.result.audited}
        skipped = {name.split(" [")[0] for name, _ in self.result.skipped}
        unaccounted = sorted(set(get_registered_routes()) - audited - skipped)
        self.assertEqual(
            unaccounted,
            [],
            "These routes were neither audited nor skipped with a reason. Add fixture "
            "kwargs or an exclusion in flipfix/apps/core/mobile_parity/routes.py: "
            f"{unaccounted}",
        )

    def test_static_exclusions_all_carry_a_reason(self):
        """An exclusion without a reason is indistinguishable from an oversight."""
        for name in get_registered_routes():
            reason = static_exclusion(name)
            if reason is not None:
                self.assertTrue(reason.strip(), f"{name} is excluded with an empty reason.")

    def test_the_audit_covered_a_meaningful_share_of_the_site(self):
        """Guard against a silent collapse to zero, which would look like success."""
        self.assertGreater(
            len(self.result.audited),
            len(get_registered_routes()) // 3,
            "The parity audit rendered far fewer pages than expected — the gate would "
            "pass without checking anything.",
        )


@tag("unit")
class RouteEnumerationTests(SimpleTestCase):
    """Enumeration must tell "not a page here" apart from "nobody mapped this"."""

    def test_names_absent_from_the_urlconf_are_skipped(self):
        """The access registry is process-global.

        ``test_routing.py`` wires dummy views through our ``path()`` to exercise
        the access levels, which leaves names like ``test-public`` in the
        registry for the rest of the run. They are not pages of this site, and
        must not abort the audit when that module happens to import first.
        """
        with mock.patch.object(
            parity_routes, "get_registered_routes", return_value={"test-always-public": None}
        ):
            audited, skipped = parity_routes.enumerate_routes(mock.MagicMock())

        self.assertEqual(audited, [])
        self.assertEqual(skipped, [("test-always-public", "not part of the active URLconf")])

    def test_a_real_route_without_fixture_kwargs_still_fails_loudly(self):
        """The guard above must not become a way to lose coverage silently."""
        without_machine_edit = {
            name: builder
            for name, builder in parity_routes.ROUTE_KWARGS.items()
            if name != "machine-edit"
        }
        with (
            mock.patch.object(
                parity_routes, "get_registered_routes", return_value={"machine-edit": None}
            ),
            mock.patch.object(parity_routes, "ROUTE_KWARGS", without_machine_edit),
            self.assertRaisesMessage(UnmappedRouteError, "machine-edit"),
        ):
            parity_routes.enumerate_routes(mock.MagicMock())
