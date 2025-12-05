"""Reference extraction from Discord messages."""

from __future__ import annotations

import re

from .types import ParsedReference, ReferenceType


def parse_url(url: str) -> ParsedReference | None:
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
    # /parts/updates/99/
    # /machines/medieval-madness/
    # Note: /parts/updates/ must come before /parts/ to match correctly
    patterns = [
        (r"/problem-reports/(\d+)", ReferenceType.PROBLEM_REPORT),
        (r"/logs/(\d+)", ReferenceType.LOG_ENTRY),
        (r"/parts/updates/(\d+)", ReferenceType.PART_REQUEST_UPDATE),
        (r"/parts/(\d+)", ReferenceType.PART_REQUEST),
        (r"/machines/([a-z0-9-]+)", ReferenceType.MACHINE),
    ]

    for pattern, ref_type in patterns:
        match = re.search(pattern, url)
        if match:
            value = match.group(1)
            if ref_type == ReferenceType.MACHINE:
                return ParsedReference(ref_type=ref_type, machine_slug=value)
            else:
                return ParsedReference(ref_type=ref_type, object_id=int(value))

    return None


def parse_explicit_references(content: str) -> list[ParsedReference]:
    """Parse explicit ID references like 'PR #123' or 'Parts #45'."""
    refs = []

    # Match "PR #123", "PR-123", "PR123"
    pr_matches = re.findall(r"\bPR\s*[#-]?\s*(\d+)\b", content, re.IGNORECASE)
    for match in pr_matches:
        refs.append(ParsedReference(ref_type=ReferenceType.PROBLEM_REPORT, object_id=int(match)))

    # Match "Parts #45", "Part #45", "Parts-45"
    parts_matches = re.findall(r"\bParts?\s*[#-]?\s*(\d+)\b", content, re.IGNORECASE)
    for match in parts_matches:
        refs.append(ParsedReference(ref_type=ReferenceType.PART_REQUEST, object_id=int(match)))

    return refs
