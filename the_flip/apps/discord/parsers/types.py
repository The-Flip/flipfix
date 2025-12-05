"""Type definitions for Discord message parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.maintenance.models import ProblemReport
    from the_flip.apps.parts.models import PartRequest


class RecordType(Enum):
    """Type of record to create from a Discord message."""

    LOG_ENTRY = "log_entry"
    PROBLEM_REPORT = "problem_report"
    PART_REQUEST = "part_request"
    PART_REQUEST_UPDATE = "part_request_update"


class ReferenceType(Enum):
    """Type of reference parsed from a URL or explicit mention in a Discord message."""

    LOG_ENTRY = "log_entry"
    PROBLEM_REPORT = "problem_report"
    PART_REQUEST = "part_request"
    PART_REQUEST_UPDATE = "part_request_update"
    MACHINE = "machine"


@dataclass
class ParsedReference:
    """A reference parsed from a Discord message."""

    ref_type: ReferenceType
    object_id: int | None = None
    machine_slug: str | None = None


@dataclass
class ParseResult:
    """Result of parsing a Discord message."""

    # What type of record to create (None means ignore/don't create)
    record_type: RecordType | None

    # Context found
    machine: MachineInstance | None = None
    problem_report: ProblemReport | None = None
    part_request: PartRequest | None = None

    # Why we chose this record type (for logging)
    reason: str = ""
