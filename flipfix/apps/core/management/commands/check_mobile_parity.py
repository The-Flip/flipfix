"""Report UI affordances that are reachable on desktop but not on mobile.

The site keeps its page actions in two places — ``{% block mobile_actions %}``
and ``{% block sidebar %}`` — and which one you see is decided purely by CSS.
Keeping the two in step is manual, so they drift. This command renders every
page at a narrow and a wide viewport, resolves what each one actually displays,
and reports the difference.

See ``docs/MobileParity.md`` for the design and its blind spots.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment

from flipfix.apps.core.mobile_parity.audit import AuditResult, Gap, run_audit
from flipfix.apps.core.mobile_parity.baseline import (
    BASELINE_PATH,
    BaselineDiff,
    build_updated,
    diff_against,
    load_baseline,
    write_baseline,
)
from flipfix.apps.core.mobile_parity.config import DESKTOP_WIDTH, MOBILE_WIDTH
from flipfix.apps.core.mobile_parity.routes import PERSONAS_BY_ACCESS


class _RollbackError(Exception):
    """Signal that unwinds the fixture transaction, carrying the finished audit."""

    def __init__(self, result: AuditResult) -> None:
        super().__init__("discarding parity audit fixtures")
        self.result = result


def _persona_names() -> list[str]:
    return sorted({persona.name for group in PERSONAS_BY_ACCESS.values() for persona in group})


class Command(BaseCommand):
    help = "Find UI affordances available on desktop but missing on mobile."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Rewrite the baseline, dropping entries that no longer reproduce.",
        )
        parser.add_argument(
            "--accept-new",
            action="store_true",
            help="With --update-baseline, also record newly found gaps.",
        )
        parser.add_argument("--route", action="append", help="Audit only this route name.")
        parser.add_argument(
            "--persona", action="append", choices=_persona_names(), help="Audit only this persona."
        )
        parser.add_argument("--mobile-width", type=int, default=MOBILE_WIDTH)
        parser.add_argument("--desktop-width", type=int, default=DESKTOP_WIDTH)
        parser.add_argument(
            "--fail-on",
            choices=("action", "any", "none"),
            default="any",
            help="Which findings make the command exit non-zero. Default: any.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["accept_new"] and not options["update_baseline"]:
            raise CommandError("--accept-new only makes sense together with --update-baseline.")

        result = self._audit(options)
        baseline = load_baseline()
        diff = diff_against(result, baseline)

        if options["update_baseline"]:
            updated = build_updated(result, baseline, accept_new=options["accept_new"])
            write_baseline(updated)

        if options["json"]:
            self.stdout.write(json.dumps(self._as_json(result, diff), indent=2, sort_keys=True))
        else:
            self._report(result, diff, options)

        if self._should_fail(result, diff, options):
            raise CommandError("Mobile parity check failed. See the findings above.")

    # -- running ------------------------------------------------------------

    def _audit(self, options: dict[str, Any]) -> AuditResult:
        """Run the audit against a throwaway test database.

        The audit needs realistic objects to render against, so it builds
        fixtures the same way the test suite does. Those must never touch a real
        database, hence the test-database dance plus a rolled-back transaction.
        """
        setup_test_environment()
        runner = DiscoverRunner(verbosity=0, interactive=False, keepdb=True)
        old_config = runner.setup_databases()
        try:
            with transaction.atomic():
                raise _RollbackError(
                    run_audit(
                        route_names=options["route"],
                        persona_names=options["persona"],
                        mobile_width=options["mobile_width"],
                        desktop_width=options["desktop_width"],
                    )
                )
        except _RollbackError as signal:
            return signal.result
        finally:
            runner.teardown_databases(old_config)
            teardown_test_environment()

    def _should_fail(
        self, result: AuditResult, diff: BaselineDiff, options: dict[str, Any]
    ) -> bool:
        if options["fail_on"] == "none" or options["update_baseline"]:
            return False
        if diff.stale:
            return True
        if options["fail_on"] == "action":
            return any(gap.is_action for gap in diff.new)
        return bool(diff.new)

    # -- reporting ----------------------------------------------------------

    def _report(self, result: AuditResult, diff: BaselineDiff, options: dict[str, Any]) -> None:
        index = result.index
        write = self.stdout.write

        write(self.style.MIGRATE_HEADING("Mobile UI parity audit"))
        write(
            f"  CSS       {index.source} — {len(index.toggle_classes())} viewport toggle "
            f"classes, breakpoints {'/'.join(str(width) for width in index.breakpoints)}"
        )
        write(f"  Widths    mobile {result.mobile_width}px  vs  desktop {result.desktop_width}px")
        write(f"  Pages     {len(result.audited)} audited, {len(result.skipped)} skipped")

        self._write_findings(result.actions, "ERRORS", "actions reachable only on desktop", "ERROR")
        self._write_findings(
            result.content, "WARNINGS", "content visible only on desktop", "WARNING"
        )
        self._write_baseline_status(diff, options)

    def _write_findings(
        self, gaps: tuple[Gap, ...], heading: str, subtitle: str, style_name: str
    ) -> None:
        style = getattr(self.style, style_name)
        self.stdout.write("")
        self.stdout.write(style(f"{heading} — {subtitle} ({len(gaps)})"))
        if not gaps:
            self.stdout.write("  none")
            return
        current = None
        for gap in gaps:
            header = f"{gap.route} [{gap.persona}]"
            if header != current:
                self.stdout.write("")
                self.stdout.write(f"  {header}")
                current = header
            self.stdout.write(f"    {gap.key}  <{gap.element}> {gap.label!r}")
            revealed = f", revealed at {gap.revealed_at}px" if gap.revealed_at else ""
            self.stdout.write(f"        hidden by {gap.hidden_by}{revealed}")

    def _write_baseline_status(self, diff: BaselineDiff, options: dict[str, Any]) -> None:
        write = self.stdout.write
        write("")
        write(self.style.MIGRATE_HEADING(f"BASELINE  {BASELINE_PATH}"))
        write(f"  ok  {len(diff.reproduced)} known gaps reproduced")
        write(f"  ok  {len(diff.accepted_reproduced)} accepted differences reproduced")

        if diff.new:
            write(self.style.ERROR(f"  x   {len(diff.new)} NEW gaps not in the baseline"))
            for gap in diff.new:
                write(f"        {gap.route} [{gap.persona}] {gap.key}")
        if diff.stale:
            write(
                self.style.ERROR(
                    f"  x   {len(diff.stale)} STALE entries — they no longer reproduce, delete them"
                )
            )
            for entry in diff.stale:
                write(f"        {entry.route} [{entry.persona}] {entry.key}")

        if options["update_baseline"]:
            write("")
            write(self.style.SUCCESS(f"  baseline rewritten: {BASELINE_PATH}"))
        elif not diff.is_clean:
            write("")
            write("  Fix the markup, or record the gap:")
            write("    python manage.py check_mobile_parity --update-baseline --accept-new")

    def _as_json(self, result: AuditResult, diff: BaselineDiff) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "widths": {"mobile": result.mobile_width, "desktop": result.desktop_width},
            "pages": {
                "audited": [{"route": route, "persona": who} for route, who in result.audited],
                "skipped": [{"route": route, "reason": why} for route, why in result.skipped],
            },
            "gaps": [
                {
                    "route": gap.route,
                    "persona": gap.persona,
                    "key": gap.key,
                    "kind": gap.kind,
                    "severity": "error" if gap.is_action else "warning",
                    "element": gap.element,
                    "label": gap.label,
                    "hidden_by": gap.hidden_by,
                    "revealed_at": gap.revealed_at,
                }
                for gap in result.gaps
            ],
            "baseline": {
                "known": len(diff.reproduced),
                "accepted": len(diff.accepted_reproduced),
                "new": len(diff.new),
                "stale": len(diff.stale),
            },
        }
