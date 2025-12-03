"""Discord message parsing for ticket creation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.maintenance.models import ProblemReport
    from the_flip.apps.parts.models import PartRequest

logger = logging.getLogger(__name__)


# Keywords for classification (single words only - matched via word splitting)
PARTS_KEYWORDS = {"need", "order", "part", "parts", "buy", "purchase", "ordering"}
PROBLEM_KEYWORDS = {"broken", "stuck", "dead", "issue", "problem"}
WORK_KEYWORDS = {
    "fixed",
    "replaced",
    "cleaned",
    "adjusted",
    "repaired",
    "installed",
    "swapped",
    "changed",
}

# Phrases for classification (multi-word - matched via substring)
PROBLEM_PHRASES = ["not working", "doesnt work", "doesn't work", "won't start", "wont start"]
WORK_PHRASES = ["worked on"]


@dataclass
class ParsedReference:
    """A reference parsed from a Discord message."""

    ref_type: str  # "problem_report", "part_request", "log_entry", "machine"
    object_id: int | None = None
    machine_slug: str | None = None


@dataclass
class ParseResult:
    """Result of parsing a Discord message."""

    # What type of record to create
    action: str  # "log_entry", "problem_report", "part_request", "part_request_update", "ignore"

    # Context found
    machine: MachineInstance | None = None
    problem_report: ProblemReport | None = None
    part_request: PartRequest | None = None

    # Why we chose this action (for logging)
    reason: str = ""

    # Confidence level
    confident: bool = True


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
    from the_flip.apps.parts.models import PartRequest

    # 1. Check if replying to a webhook post with a URL
    if reply_to_embed_url:
        ref = _parse_url(reply_to_embed_url)
        if ref:
            if ref.ref_type == "problem_report" and ref.object_id:
                pr = ProblemReport.objects.filter(pk=ref.object_id).first()
                if pr:
                    return ParseResult(
                        action="log_entry",
                        problem_report=pr,
                        machine=pr.machine,
                        reason=f"Reply to problem report #{pr.pk}",
                    )
            elif ref.ref_type == "part_request" and ref.object_id:
                part_req = PartRequest.objects.filter(pk=ref.object_id).first()
                if part_req:
                    return ParseResult(
                        action="part_request_update",
                        part_request=part_req,
                        machine=part_req.machine,
                        reason=f"Reply to part request #{part_req.pk}",
                    )
            elif ref.ref_type == "log_entry" and ref.object_id:
                from the_flip.apps.maintenance.models import LogEntry

                log = (
                    LogEntry.objects.select_related("machine", "problem_report")
                    .filter(pk=ref.object_id)
                    .first()
                )
                if log:
                    return ParseResult(
                        action="log_entry",
                        problem_report=log.problem_report,
                        machine=log.machine,
                        reason=f"Reply to log entry #{log.pk}",
                    )

    # 2. Check for explicit references in the message
    refs = _parse_explicit_references(content)
    for ref in refs:
        if ref.ref_type == "problem_report" and ref.object_id:
            pr = ProblemReport.objects.filter(pk=ref.object_id).first()
            if pr:
                return ParseResult(
                    action="log_entry",
                    problem_report=pr,
                    machine=pr.machine,
                    reason=f"Explicit PR #{pr.pk} reference",
                )
        elif ref.ref_type == "part_request" and ref.object_id:
            part_req = PartRequest.objects.filter(pk=ref.object_id).first()
            if part_req:
                return ParseResult(
                    action="part_request_update",
                    part_request=part_req,
                    machine=part_req.machine,
                    reason=f"Explicit Parts #{part_req.pk} reference",
                )

    # 3. Check for URLs in message
    urls = re.findall(r"https?://[^\s]+", content)
    for url in urls:
        ref = _parse_url(url)
        if ref:
            if ref.ref_type == "problem_report" and ref.object_id:
                pr = ProblemReport.objects.filter(pk=ref.object_id).first()
                if pr:
                    return ParseResult(
                        action="log_entry",
                        problem_report=pr,
                        machine=pr.machine,
                        reason=f"URL to problem report #{pr.pk}",
                    )
            elif ref.ref_type == "part_request" and ref.object_id:
                part_req = PartRequest.objects.filter(pk=ref.object_id).first()
                if part_req:
                    return ParseResult(
                        action="part_request_update",
                        part_request=part_req,
                        machine=part_req.machine,
                        reason=f"URL to part request #{part_req.pk}",
                    )
            elif ref.ref_type == "machine" and ref.machine_slug:
                machine = MachineInstance.objects.filter(slug=ref.machine_slug).first()
                if machine:
                    # Continue to classify with this machine
                    return _classify_with_machine(content, machine)

    # 4. Try to find a machine reference
    machine = _find_machine(content)
    if machine:
        return _classify_with_machine(content, machine)

    # 5. No context found - ignore
    return ParseResult(
        action="ignore",
        reason="No machine or ticket reference found",
        confident=True,
    )


def _parse_url(url: str) -> ParsedReference | None:
    """Parse a theflip.app URL to extract object references.

    Only parses URLs from known valid domains (DISCORD_VALID_DOMAINS setting)
    to avoid false matches on random URLs in messages.
    """
    from urllib.parse import urlparse

    from django.conf import settings

    valid_domains = getattr(settings, "DISCORD_VALID_DOMAINS", ["theflip.app"])

    # Validate the domain
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Check if hostname matches or ends with a valid domain
        if not any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in valid_domains
        ):
            return None
    except Exception:
        return None

    # Match patterns like:
    # /problem-reports/123/
    # /logs/456/
    # /parts/78/
    # /machines/medieval-madness/
    patterns = [
        (r"/problem-reports/(\d+)", "problem_report"),
        (r"/logs/(\d+)", "log_entry"),
        (r"/parts/(\d+)", "part_request"),
        (r"/machines/([a-z0-9-]+)", "machine"),
    ]

    for pattern, ref_type in patterns:
        match = re.search(pattern, url)
        if match:
            value = match.group(1)
            if ref_type == "machine":
                return ParsedReference(ref_type=ref_type, machine_slug=value)
            else:
                return ParsedReference(ref_type=ref_type, object_id=int(value))

    return None


def _parse_explicit_references(content: str) -> list[ParsedReference]:
    """Parse explicit ID references like 'PR #123' or 'Parts #45'."""
    refs = []

    # Match "PR #123", "PR-123", "PR123"
    pr_matches = re.findall(r"\bPR\s*[#-]?\s*(\d+)\b", content, re.IGNORECASE)
    for match in pr_matches:
        refs.append(ParsedReference(ref_type="problem_report", object_id=int(match)))

    # Match "Parts #45", "Part #45", "Parts-45"
    parts_matches = re.findall(r"\bParts?\s*[#-]?\s*(\d+)\b", content, re.IGNORECASE)
    for match in parts_matches:
        refs.append(ParsedReference(ref_type="part_request", object_id=int(match)))

    return refs


def _find_machine(content: str) -> MachineInstance | None:
    """Find a machine reference in the message content.

    Returns the machine if exactly one match is found, None otherwise.
    """
    from the_flip.apps.catalog.models import get_machines_for_matching

    content_lower = content.lower()

    # Get all active machines (cached in catalog app)
    machines = get_machines_for_matching()

    matches = []

    for machine in machines:
        model_name = machine.model.name.lower()
        slug = machine.slug.lower()

        # Exact match on slug
        if slug in content_lower:
            matches.append((machine, "exact_slug"))
            continue

        # Exact match on model name
        if model_name in content_lower:
            matches.append((machine, "exact_name"))
            continue

        # Prefix match: "godzilla" matches "godzilla (premium)"
        # Split model name into first word for prefix matching
        first_word = model_name.split()[0] if model_name else ""
        if first_word and len(first_word) >= 4:  # Avoid short matches
            # Check if first word appears as a whole word in content
            if re.search(rf"\b{re.escape(first_word)}\b", content_lower):
                matches.append((machine, "prefix"))

    # Remove duplicates (same machine matched multiple ways)
    unique_machines = {}
    for machine, match_type in matches:
        if machine.pk not in unique_machines:
            unique_machines[machine.pk] = (machine, match_type)

    if len(unique_machines) == 1:
        machine, match_type = list(unique_machines.values())[0]
        logger.info(
            "discord_machine_matched",
            extra={
                "machine_id": machine.pk,
                "machine_name": machine.display_name,
                "match_type": match_type,
            },
        )
        return machine
    elif len(unique_machines) > 1:
        logger.info(
            "discord_machine_ambiguous",
            extra={
                "matches": [m.display_name for m, _ in unique_machines.values()],
                "content_preview": content[:100],
            },
        )
        return None
    else:
        return None


def _has_keywords(
    content_lower: str, words: set[str], keywords: set[str], phrases: list[str] | None = None
) -> bool:
    """Check if content contains any of the keywords or phrases."""
    # Check single-word keywords
    if words & keywords:
        return True
    # Check multi-word phrases
    if phrases:
        for phrase in phrases:
            if phrase in content_lower:
                return True
    return False


def _classify_with_machine(content: str, machine: MachineInstance) -> ParseResult:
    """Classify a message when we know the machine."""
    from the_flip.apps.maintenance.models import ProblemReport

    content_lower = content.lower()
    words = set(content_lower.split())

    # Check for parts keywords
    if _has_keywords(content_lower, words, PARTS_KEYWORDS):
        return ParseResult(
            action="part_request",
            machine=machine,
            reason=f"Parts keywords found, machine: {machine.display_name}",
        )

    # Check for problem keywords/phrases
    if _has_keywords(content_lower, words, PROBLEM_KEYWORDS, PROBLEM_PHRASES):
        return ParseResult(
            action="problem_report",
            machine=machine,
            reason=f"Problem keywords found, machine: {machine.display_name}",
        )

    # Fetch open problem report once (used for work keywords and default case)
    open_pr = (
        ProblemReport.objects.filter(machine=machine, status="open").order_by("-created_at").first()
    )

    # Check for work keywords/phrases - link to open problem report if exists
    if _has_keywords(content_lower, words, WORK_KEYWORDS, WORK_PHRASES):
        if open_pr:
            return ParseResult(
                action="log_entry",
                machine=machine,
                problem_report=open_pr,
                reason=f"Work keywords, linked to open PR #{open_pr.pk}",
            )
        else:
            return ParseResult(
                action="log_entry",
                machine=machine,
                reason=f"Work keywords, no open PR, machine: {machine.display_name}",
            )

    # Default to log entry if we have a machine but no clear classification
    if open_pr:
        return ParseResult(
            action="log_entry",
            machine=machine,
            problem_report=open_pr,
            reason=f"Default to log, linked to open PR #{open_pr.pk}",
            confident=False,
        )

    return ParseResult(
        action="log_entry",
        machine=machine,
        reason=f"Default to standalone log, machine: {machine.display_name}",
        confident=False,
    )
