"""Render the daily maintenance report to stdout (and optionally post it)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from flipfix.apps.maintenance.reports import (
    build_report,
    render_markdown,
    render_verbose_text,
)


class Command(BaseCommand):
    help = "Render the daily maintenance report: the compact emoji digest, or --verbose."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show a per-machine breakdown of why each machine got its emoji.",
        )

    def handle(self, *args: object, **options: object) -> None:
        report = build_report()
        if options["verbose"]:
            self.stdout.write(render_verbose_text(report))
        else:
            self.stdout.write(render_markdown(report))
