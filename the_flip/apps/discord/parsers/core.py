"""Core message parsing logic."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .intent import classify_intent, has_work_keywords
from .machines import find_machine_name
from .references import parse_explicit_references, parse_url
from .types import ParseResult, RecordType, ReferenceType

if TYPE_CHECKING:
    from the_flip.apps.catalog.models import MachineInstance


def parse_message(
    content: str,
    reply_to_embed_url: str | None = None,
) -> ParseResult:
    """Parse a Discord message to determine what action to take.

    Args:
        content: The message text
        reply_to_embed_url: If replying to our webhook, the URL from the embed

    Returns:
        ParseResult with action and context
    """
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.maintenance.models import ProblemReport
    from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

    # 1. Check if replying to a webhook post with a URL
    if reply_to_embed_url:
        ref = parse_url(reply_to_embed_url)
        if ref:
            if ref.ref_type == ReferenceType.PROBLEM_REPORT and ref.object_id:
                pr = ProblemReport.objects.filter(pk=ref.object_id).first()
                if pr:
                    return ParseResult(
                        record_type=RecordType.LOG_ENTRY,
                        problem_report=pr,
                        machine=pr.machine,
                        reason=f"Reply to problem report #{pr.pk}",
                    )
            elif ref.ref_type == ReferenceType.PART_REQUEST and ref.object_id:
                part_req = PartRequest.objects.filter(pk=ref.object_id).first()
                if part_req:
                    return ParseResult(
                        record_type=RecordType.PART_REQUEST_UPDATE,
                        part_request=part_req,
                        machine=part_req.machine,
                        reason=f"Reply to part request #{part_req.pk}",
                    )
            elif ref.ref_type == ReferenceType.LOG_ENTRY and ref.object_id:
                from the_flip.apps.maintenance.models import LogEntry

                log = (
                    LogEntry.objects.select_related("machine", "problem_report")
                    .filter(pk=ref.object_id)
                    .first()
                )
                if log:
                    return ParseResult(
                        record_type=RecordType.LOG_ENTRY,
                        problem_report=log.problem_report,
                        machine=log.machine,
                        reason=f"Reply to log entry #{log.pk}",
                    )
            elif ref.ref_type == ReferenceType.PART_REQUEST_UPDATE and ref.object_id:
                update = (
                    PartRequestUpdate.objects.select_related(
                        "part_request", "part_request__machine"
                    )
                    .filter(pk=ref.object_id)
                    .first()
                )
                if update:
                    return ParseResult(
                        record_type=RecordType.PART_REQUEST_UPDATE,
                        part_request=update.part_request,
                        machine=update.part_request.machine,
                        reason=f"Reply to part request update #{update.pk}",
                    )

    # 2. Check for explicit references in the message
    refs = parse_explicit_references(content)
    for ref in refs:
        if ref.ref_type == ReferenceType.PROBLEM_REPORT and ref.object_id:
            pr = ProblemReport.objects.filter(pk=ref.object_id).first()
            if pr:
                return ParseResult(
                    record_type=RecordType.LOG_ENTRY,
                    problem_report=pr,
                    machine=pr.machine,
                    reason=f"Explicit PR #{pr.pk} reference",
                )
        elif ref.ref_type == ReferenceType.PART_REQUEST and ref.object_id:
            part_req = PartRequest.objects.filter(pk=ref.object_id).first()
            if part_req:
                return ParseResult(
                    record_type=RecordType.PART_REQUEST_UPDATE,
                    part_request=part_req,
                    machine=part_req.machine,
                    reason=f"Explicit Parts #{part_req.pk} reference",
                )

    # 3. Check for URLs in message
    urls = re.findall(r"https?://[^\s]+", content)
    for url in urls:
        ref = parse_url(url)
        if ref:
            if ref.ref_type == ReferenceType.PROBLEM_REPORT and ref.object_id:
                pr = ProblemReport.objects.filter(pk=ref.object_id).first()
                if pr:
                    return ParseResult(
                        record_type=RecordType.LOG_ENTRY,
                        problem_report=pr,
                        machine=pr.machine,
                        reason=f"URL to problem report #{pr.pk}",
                    )
            elif ref.ref_type == ReferenceType.PART_REQUEST and ref.object_id:
                part_req = PartRequest.objects.filter(pk=ref.object_id).first()
                if part_req:
                    return ParseResult(
                        record_type=RecordType.PART_REQUEST_UPDATE,
                        part_request=part_req,
                        machine=part_req.machine,
                        reason=f"URL to part request #{part_req.pk}",
                    )
            elif ref.ref_type == ReferenceType.PART_REQUEST_UPDATE and ref.object_id:
                update = (
                    PartRequestUpdate.objects.select_related(
                        "part_request", "part_request__machine"
                    )
                    .filter(pk=ref.object_id)
                    .first()
                )
                if update:
                    return ParseResult(
                        record_type=RecordType.PART_REQUEST_UPDATE,
                        part_request=update.part_request,
                        machine=update.part_request.machine,
                        reason=f"URL to part request update #{update.pk}",
                    )
            elif ref.ref_type == ReferenceType.MACHINE and ref.machine_slug:
                machine = MachineInstance.objects.filter(slug=ref.machine_slug).first()
                if machine:
                    # Continue to classify with this machine
                    return _classify_with_machine(content, machine)

    # 4. Try to find a machine reference by name
    from the_flip.apps.catalog.models import get_machines_for_matching

    machines = get_machines_for_matching()
    machine_names = [m.display_name for m in machines]
    matched_name = find_machine_name(content, machine_names)
    if matched_name:
        # Look up the machine by display_name
        machine = next((m for m in machines if m.display_name == matched_name), None)
        if machine:
            return _classify_with_machine(content, machine)

    # 5. No context found - ignore
    return ParseResult(
        record_type=None,
        reason="No machine or ticket reference found",
    )


def _classify_with_machine(content: str, machine: MachineInstance) -> ParseResult:
    """Classify a message when we know the machine.

    Uses classify_intent for keyword matching, then handles database
    lookups for linking to open problem reports.
    """
    from the_flip.apps.maintenance.models import ProblemReport

    record_type = classify_intent(content)

    # Parts and problem don't need PR lookup
    if record_type == RecordType.PART_REQUEST:
        return ParseResult(
            record_type=record_type,
            machine=machine,
            reason=f"Parts keywords found, machine: {machine.display_name}",
        )

    if record_type == RecordType.PROBLEM_REPORT:
        return ParseResult(
            record_type=record_type,
            machine=machine,
            reason=f"Problem keywords found, machine: {machine.display_name}",
        )

    # LOG_ENTRY - try to link to open problem report
    open_pr = (
        ProblemReport.objects.filter(machine_id=machine.pk, status="open")
        .order_by("-created_at")
        .first()
    )

    # Determine reason based on whether we matched work keywords
    work_keywords_found = has_work_keywords(content)

    if open_pr:
        reason = (
            f"Work keywords, linked to open PR #{open_pr.pk}"
            if work_keywords_found
            else f"Default to log, linked to open PR #{open_pr.pk}"
        )
        return ParseResult(
            record_type=RecordType.LOG_ENTRY,
            machine=machine,
            problem_report=open_pr,
            reason=reason,
        )

    reason = (
        f"Work keywords, no open PR, machine: {machine.display_name}"
        if work_keywords_found
        else f"Default to standalone log, machine: {machine.display_name}"
    )
    return ParseResult(
        record_type=RecordType.LOG_ENTRY,
        machine=machine,
        reason=reason,
    )
