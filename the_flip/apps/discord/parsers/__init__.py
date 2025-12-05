"""Discord message parsing for ticket creation.

This package provides parsing and classification of Discord messages
to determine what maintenance records to create.

Public API:
- parse_message: Main entry point for parsing Discord messages
- RecordType: Enum of record types that can be created
- ReferenceType: Enum of reference types found in messages
- ParseResult: Result of parsing a message
- ParsedReference: A reference found in a message
- find_machine_name: Pure function for matching machine names
- classify_intent: Pure function for classifying message intent
"""

from .core import parse_message
from .intent import classify_intent
from .machines import find_machine_name
from .types import ParsedReference, ParseResult, RecordType, ReferenceType

__all__ = [
    "parse_message",
    "RecordType",
    "ReferenceType",
    "ParseResult",
    "ParsedReference",
    "find_machine_name",
    "classify_intent",
]
