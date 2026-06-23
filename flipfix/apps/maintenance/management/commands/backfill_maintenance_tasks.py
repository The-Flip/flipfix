"""Backfill maintenance-task tags from existing data.

Two sources, both reviewable via the default dry-run and idempotent on ``--apply``:

(a) **Work logs** — keyword matches in existing ``LogEntry.text`` add the matching
    task tag to that entry. Matching is done in Python (``re``) so it behaves
    identically on SQLite and PostgreSQL.

(b) **Completed intakes** — a *closed* intake ``ProblemReport`` whose checklist is
    substantially completed credits the three seed tasks (clean playfield, replace
    balls, replace rubbers) at the intake's completion date, via a synthetic
    ``LogEntry``. Intake is an *evaluation* checklist, so this is an approximation;
    it has no "balls" item, hence the all-three crediting is intentional.

Run without ``--apply`` to review proposals, then re-run with ``--apply``.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from flipfix.apps.maintenance.models import LogEntry, MaintenanceTaskType, ProblemReport

# (a) Work-log keyword patterns per task slug (case-insensitive). Deliberately
# broad; the dry-run is the review surface for false positives.
WORK_LOG_PATTERNS: dict[str, list[str]] = {
    "clean-playfield": [
        r"\bclean(?:ed|ing)?\b[^.\n]*\bplayfield\b",
        r"\bplayfield\b[^.\n]*\bclean",
        r"\bwax(?:ed|ing)?\b[^.\n]*\bplayfield\b",
        r"\bnovus\b",
    ],
    "replace-balls": [
        r"\b(?:replac|swap|chang)(?:e|ed|ing)\b[^.\n]*\bballs?\b",
        r"\bnew\b[^.\n]*\bpinballs?\b",
        r"\bnew balls?\b",
    ],
    "replace-rubbers": [
        r"\b(?:new|replac|swap|chang)(?:e|ed|ing)?\b[^.\n]*\b(?:rubber|elastic|ring)s?\b",
        r"\brubber kit\b",
        r"\bre-?rubber",
    ],
}

# (b) Intake detection + crediting.
INTAKE_SIGNATURE = re.compile(
    r"acquisition evaluation checklist|inside backbox|while playing",
    re.IGNORECASE,
)
INTAKE_TASK_SLUGS = ["clean-playfield", "replace-balls", "replace-rubbers"]
INTAKE_BACKFILL_MARKER = "Intake completed — crediting routine maintenance"
# GFM task-list bullet at line start (mirrors static/core/checkbox_toggle.js), so
# inline "[x]" text and markdown links are not miscounted.
CHECKBOX_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[([ xX])\]", re.MULTILINE)


class Command(BaseCommand):
    help = "Backfill maintenance-task tags from existing log entries and completed intakes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes. Without this flag the command only reports (dry-run).",
        )
        parser.add_argument(
            "--task",
            help="Limit work-log matching to a single task slug (skips intake crediting).",
        )
        parser.add_argument(
            "--intake-threshold",
            type=float,
            default=0.8,
            help="Fraction of intake checkboxes that must be checked to credit (default 0.8).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        only_task = options.get("task")
        threshold = options["intake_threshold"]
        if not 0 <= threshold <= 1:
            raise CommandError("--intake-threshold must be between 0 and 1.")
        tasks = {t.slug: t for t in MaintenanceTaskType.objects.all()}

        self._backfill_work_logs(tasks, only_task, apply)
        if not only_task:
            self._backfill_intakes(tasks, threshold, apply)

        if not apply:
            self.stdout.write(self.style.WARNING("\nDry run — re-run with --apply to commit."))

    # ---- (a) work-log keyword matching -------------------------------------

    def _backfill_work_logs(self, tasks, only_task, apply):
        compiled = {
            slug: [re.compile(p, re.IGNORECASE) for p in patterns]
            for slug, patterns in WORK_LOG_PATTERNS.items()
            if slug in tasks and (not only_task or slug == only_task)
        }
        if only_task and only_task not in compiled:
            raise CommandError(f"Unknown/unsupported task slug: {only_task}")

        self.stdout.write(self.style.MIGRATE_HEADING("Work-log keyword matches:"))
        counts = dict.fromkeys(compiled, 0)
        for entry in LogEntry.objects.select_related("machine"):
            text = entry.text or ""
            existing = set(entry.maintenance_tasks.values_list("slug", flat=True))
            for slug, regexes in compiled.items():
                if slug in existing or not any(r.search(text) for r in regexes):
                    continue
                counts[slug] += 1
                self.stdout.write(
                    f"  [{slug}] log #{entry.pk} {entry.occurred_at:%Y-%m-%d} "
                    f"{entry.machine.name}: {self._snippet(text)}"
                )
                if apply:
                    entry.maintenance_tasks.add(tasks[slug])

        total = sum(counts.values())
        summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"
        self.stdout.write(self.style.SUCCESS(f"  → {total} work-log matches ({summary})."))

    # ---- (b) completed-intake crediting ------------------------------------

    def _backfill_intakes(self, tasks, threshold, apply):
        seed_tasks = [tasks[s] for s in INTAKE_TASK_SLUGS if s in tasks]
        if not seed_tasks:
            return

        self.stdout.write(self.style.MIGRATE_HEADING("Completed-intake credits:"))
        credited = skipped = 0
        for report in ProblemReport.objects.filter(
            status=ProblemReport.Status.CLOSED
        ).select_related("machine"):
            desc = report.description or ""
            if not INTAKE_SIGNATURE.search(desc):
                continue
            boxes = CHECKBOX_RE.findall(desc)
            total = len(boxes)
            if total == 0:
                skipped += 1
                continue
            checked = sum(1 for b in boxes if b in ("x", "X"))
            if checked / total < threshold:
                skipped += 1
                continue
            # Idempotent: skip if a prior backfill entry already credits this report.
            if report.log_entries.filter(text__startswith=INTAKE_BACKFILL_MARKER).exists():
                continue

            completion = self._intake_completion_date(report)
            credited += 1
            self.stdout.write(
                f"  [intake] report #{report.pk} {completion:%Y-%m-%d} "
                f"{report.machine.name}: {checked}/{total} checked"
            )
            if apply:
                with transaction.atomic():
                    entry = LogEntry.objects.create(
                        machine=report.machine,
                        problem_report=report,
                        text=f"{INTAKE_BACKFILL_MARKER} (from problem report #{report.pk}).",
                        occurred_at=completion,
                        maintainer_names="System (intake backfill)",
                    )
                    entry.maintenance_tasks.set(seed_tasks)

        self.stdout.write(
            self.style.SUCCESS(
                f"  → {credited} intake credits created, {skipped} skipped (no/too-few checkboxes)."
            )
        )

    @staticmethod
    def _intake_completion_date(report):
        """Best estimate of when intake finished: latest linked log, else updated/occurred."""
        latest = (
            report.log_entries.order_by("-occurred_at")
            .values_list("occurred_at", flat=True)
            .first()
        )
        return latest or report.updated_at or report.occurred_at

    @staticmethod
    def _snippet(text: str, length: int = 80) -> str:
        flat = " ".join(text.split())
        return flat[:length] + ("…" if len(flat) > length else "")
