"""LLM integration for Discord bot message analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import anthropic
from anthropic.types import ToolChoiceToolParam, ToolParam
from asgiref.sync import sync_to_async
from constance import config
from decouple import config as decouple_config

from the_flip.apps.catalog.models import MachineInstance

if TYPE_CHECKING:
    from the_flip.apps.discord import context as context_module

logger = logging.getLogger(__name__)


class RecordType(StrEnum):
    """Valid record types for Discord bot suggestions."""

    LOG_ENTRY = "log_entry"
    PROBLEM_REPORT = "problem_report"
    PART_REQUEST = "part_request"
    PART_REQUEST_UPDATE = "part_request_update"


@dataclass
class ChildSuggestion:
    """A child record to create alongside a parent (e.g., log_entry under problem_report)."""

    description: str
    source_message_ids: list[str]
    author_id: str  # Discord user ID of the message author


@dataclass
class RecordSuggestion:
    """A suggested record to create from Discord messages."""

    record_type: RecordType
    description: str
    source_message_ids: list[str]
    author_id: str  # Discord user ID of the message author
    slug: str | None = None  # Required for log_entry/problem_report, optional for parts
    parent_record_id: int | None = None  # log_entry→problem_report, update→part_request
    children: list[ChildSuggestion] | None = None  # Nested children to create with this parent


@dataclass
class FlattenedSuggestion:
    """A suggestion with optional parent linkage info for wizard flattening.

    When a parent suggestion has children, we flatten them into separate wizard steps.
    Each child records which parent index it belongs to, so we can skip children
    if the parent is skipped, and set parent_record_id when the parent is created.
    """

    suggestion: RecordSuggestion
    parent_index: int | None = None  # Index of parent in flattened list (None if top-level)


@dataclass
class AnalysisResult:
    """Result of LLM analysis - either suggestions or an error."""

    suggestions: list[RecordSuggestion]
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True if analysis failed."""
        return self.error is not None

    @classmethod
    def success(cls, suggestions: list[RecordSuggestion]) -> AnalysisResult:
        """Create a successful result with suggestions."""
        return cls(suggestions=suggestions, error=None)

    @classmethod
    def failure(cls, error: str) -> AnalysisResult:
        """Create a failed result with an error message."""
        return cls(suggestions=[], error=error)


def flatten_suggestions(suggestions: list[RecordSuggestion]) -> list[FlattenedSuggestion]:
    """Flatten nested suggestions into a sequential list for wizard processing.

    Parents with children are expanded: parent first, then each child as a separate step.
    Children inherit machine_id from their parent and have their record_type set based
    on the parent type:
    - problem_report children → log_entry
    - part_request children → part_request_update

    Returns FlattenedSuggestion objects that track parent-child relationships.
    """
    flattened: list[FlattenedSuggestion] = []

    for suggestion in suggestions:
        parent_index = len(flattened)
        flattened.append(FlattenedSuggestion(suggestion=suggestion, parent_index=None))

        if suggestion.children:
            # Determine child record type based on parent
            if suggestion.record_type == RecordType.PROBLEM_REPORT:
                child_type = RecordType.LOG_ENTRY
            elif suggestion.record_type == RecordType.PART_REQUEST:
                child_type = RecordType.PART_REQUEST_UPDATE
            else:
                # Other record types can't have children
                continue

            for child in suggestion.children:
                child_suggestion = RecordSuggestion(
                    record_type=child_type,
                    description=child.description,
                    source_message_ids=child.source_message_ids,
                    author_id=child.author_id,
                    slug=suggestion.slug,  # Inherit from parent
                    parent_record_id=None,  # Will be set when parent is created
                )
                flattened.append(
                    FlattenedSuggestion(suggestion=child_suggestion, parent_index=parent_index)
                )

    return flattened


SYSTEM_PROMPT = """You are analyzing a Discord messages from a pinball museum's maintenance channel.
Your job is to identify what maintenance records should be created in the museum's maintenance tracking system.

You will receive a list of Discord messages.  One of the messages (marked with is_target: true)
is the one the user right-clicked and selected 'Add to Maintenance System'.  Your job is to analyze
that message and all the surrounding messages to determine what maintenance records should be created.

## Record Types

- `log_entry`: work that was done on a machine (repairs, adjustments, cleaning)
- `problem_report`: a problem that needs attention (something broken, not working right)
- `part_request`: parts that need to be ordered
- `part_request_update`: update to an existing part request (e.g., "ordered!", "arrived", "installed")

## Input Format

You'll receive YAML with:
- `machines`: List of all pinball machines (use the `id` field for machine_id in your output)
- `messages`: Discord messages in chronological order

Message fields:
- `id`: unique message ID (include in source_message_ids when this message contributes content)
- `author`: display name of the message author
- `author_id`: Discord user ID (use this for author_id in your output to attribute the record)
- `content`: the message text
- `timestamp`: when message was posted
- `is_target`: if present, this is the message the user clicked (analyze THIS message)
- `reply_to_id`: if present, this message is a reply to another message
- `flipfix_record`: if present, this is a Flipfix webhook embed (no author_id - attribute to human reply)
- `thread`: if present, contains nested messages from a Discord thread

## Guidelines

1. **Resolved vs unresolved problems:**
   - If a problem was FIXED in the conversation → create a single `log_entry` that describes
     the issue AND the fix. Don't create a problem_report that's immediately resolved.
   - If a problem is UNRESOLVED → create a `problem_report`, with `log_entry` children for
     any work attempts or observations made while investigating.

2. **Consolidate conversational exchanges** - Back-and-forth discussion that forms one logical
   unit should become ONE record, not multiple. For example:
   - "Maybe needs new coil" → "Where are the coils?" → "In the parts bin" → "Replaced coil, didn't help"
   - This is ONE log entry: "Thought it might need a new coil. Replaced the coil from the parts
     bin but that didn't help."

3. **Separate distinct work attempts** - Create separate log entries for distinct observations
   or work attempts, even if they're from the same person. For example:
   - "Adjusted EOS switch, flipper still weak" → one log entry
   - "Maybe needs new coil" → separate log entry (different hypothesis/observation)

4. **Part requests** - Create `part_request` for the initial need, with `part_request_update`
   children for status changes ("ordered!", "arrived", "installed").

5. **Match machines to the list** - Use the machine `id` (slug) from the machines list.

6. **Parent relationships** - Use parent_record_id when appropriate:
   - log_entry can link to an existing problem_report (from flipfix_record in context)
   - part_request_update MUST link to a part_request
   - Get the ID from flipfix_record in context messages when available

7. **Source message tracking** - Include IDs of ALL messages that contributed content to each
   record's description.

8. **Author attribution** - Use the author_id from the primary message for that record. For
   consolidated records spanning multiple authors, use the author who did the main work or
   initiated the thread.

9. **No maintenance content** - If the conversation has no maintenance-related content, return
   empty array.

## Nested Records (children)

Use `children` array for:
- **problem_report** → `log_entry` children (work attempts on an unresolved problem)
- **part_request** → `part_request_update` children (status updates like "ordered!")

Children inherit machine_id from the parent. Each child needs its own description, source_message_ids,
and author_id.

## Description Guidelines

- Write coherent, narrative descriptions (not transcripts)
- Include ALL specific details: part names, symptoms, what was tried, what worked
- Consolidate back-and-forth exchanges into flowing prose
- Preserve technical details and outcomes faithfully

Example 1 - RESOLVED problem becomes single log_entry:
Messages: "godzilla's right flipper is broken" → "ok I fixed it" → "the flipper pin was bent"
Output: ONE log_entry with description: "Right flipper was broken. Fixed it - the flipper pin
was bent; we had a spare."

Example 2 - UNRESOLVED problem with work attempts:
Messages: "Flipper weak" → "Adjusted EOS switch, still weak" → "Maybe needs new coil"
Output: problem_report "Flipper weak" with children:
  - log_entry: "Adjusted EOS switch, flipper still weak"
  - log_entry: "Maybe needs new coil"

Example 3 - Consolidate conversational exchanges:
Messages: "Maybe needs new coil" → "Where are the coils?" → "Parts bin" → "Replaced it, didn't help"
Output: ONE log_entry: "Thought it might need a new coil. Replaced the coil from the parts bin
but that didn't help."
"""

# Schema for child records (nested under parent suggestions)
_CHILD_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Details of the work/update",
        },
        "source_message_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of Discord messages that contributed to this child record",
        },
        "author_id": {
            "type": "string",
            "description": "Discord user ID (author_id from the message) to attribute this record to",
        },
    },
    "required": ["description", "source_message_ids", "author_id"],
}

# Tool definition for structured output
RECORD_SUGGESTIONS_TOOL: ToolParam = {
    "name": "record_suggestions",
    "description": "Submit the maintenance record suggestions based on the Discord messages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "description": "List of suggested maintenance records. Empty array if no records should be created.",
                "items": {
                    "type": "object",
                    "properties": {
                        "record_type": {
                            "type": "string",
                            "enum": list(RecordType),
                            "description": "Type of maintenance record",
                        },
                        "description": {
                            "type": "string",
                            "description": "Details of the work/problem/parts needed",
                        },
                        "source_message_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "IDs of Discord messages that contributed to this record",
                        },
                        "author_id": {
                            "type": "string",
                            "description": "Discord user ID (author_id from the message) to attribute this record to",
                        },
                        "machine_id": {
                            "type": "string",
                            "description": "The ID of the machine from the provided list. Required for log_entry and problem_report, optional for part_request and part_request_update.",
                        },
                        "parent_record_id": {
                            "type": "integer",
                            "description": "ID of parent Flipfix record if applicable. For log_entry, this is a problem_report ID. For part_request_update, this is a part_request ID.",
                        },
                        "children": {
                            "type": "array",
                            "description": "Child records to create with this parent. problem_report can have log_entry children; part_request can have part_request_update children.",
                            "items": _CHILD_SUGGESTION_SCHEMA,
                        },
                    },
                    "required": ["record_type", "description", "source_message_ids", "author_id"],
                },
            },
        },
        "required": ["suggestions"],
    },
}

TOOL_CHOICE: ToolChoiceToolParam = {"type": "tool", "name": "record_suggestions"}


async def analyze_gathered_context(
    context: context_module.GatheredContext,
) -> AnalysisResult:
    """Use Claude to analyze gathered Discord context and suggest records to create.

    This is the new interface that uses YAML-formatted prompts with full message
    metadata (IDs, reply chains, thread nesting, webhook embeds).
    """
    api_key = await _get_api_key()
    if not api_key:
        logger.error("discord_llm_api_key_not_configured")
        return AnalysisResult.failure(
            "Anthropic API key not configured. Please contact an administrator."
        )

    # Get machine list from database
    machines = await _get_machines_for_prompt()

    # Build YAML prompt
    user_message = build_yaml_prompt(context, machines)

    logger.debug(
        "discord_llm_prompt",
        extra={"prompt": user_message},
    )

    # Count messages including nested thread messages
    message_count = sum(1 + len(m.thread) for m in context.messages)

    return await _analyze_with_prompt(user_message, message_count)


async def _analyze_with_prompt(user_message: str, message_count: int) -> AnalysisResult:
    """Common analysis logic for both legacy and new interfaces."""
    api_key = await _get_api_key()

    try:
        # Run the synchronous API call in a thread
        response = await _call_anthropic(api_key, user_message)

        logger.debug(
            "discord_llm_response",
            extra={"response": response.model_dump_json()},
        )

        # Extract tool use from response
        suggestions = _parse_tool_response(response)

        logger.info(
            "discord_llm_analysis_complete",
            extra={
                "message_count": message_count,
                "suggestion_count": len(suggestions),
            },
        )

        return AnalysisResult.success(suggestions)

    except anthropic.APIStatusError as e:
        logger.error("discord_llm_api_error", extra={"error": str(e), "status_code": e.status_code})
        if e.status_code == 529:
            return AnalysisResult.failure(
                "The AI service is temporarily overloaded. Please try again in a moment."
            )
        return AnalysisResult.failure(
            f"AI service error (code {e.status_code}). Please try again later."
        )
    except anthropic.APIError as e:
        logger.error("discord_llm_api_error", extra={"error": str(e)})
        return AnalysisResult.failure("AI service error. Please try again later.")
    except Exception as e:
        logger.exception("discord_llm_error", extra={"error": str(e)})
        return AnalysisResult.failure("Unexpected error during analysis. Please try again.")


@sync_to_async
def _get_api_key() -> str:
    """Get Anthropic API key from Constance config."""
    return config.ANTHROPIC_API_KEY


DEFAULT_MODEL = decouple_config("DISCORD_LLM_MODEL", default="claude-opus-4-5-20251101")

# Max tokens for LLM response (tool use responses are typically short)
DEFAULT_MAX_TOKENS = 1024


async def _call_anthropic(
    api_key: str,
    user_message: str,
    system_prompt: str | None = None,
    model: str | None = None,
) -> anthropic.types.Message:
    """Call Anthropic API with tool use for structured output."""
    client = anthropic.AsyncAnthropic(api_key=api_key)
    return await client.messages.create(
        model=model if model is not None else DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        system=system_prompt if system_prompt is not None else SYSTEM_PROMPT,
        tools=[RECORD_SUGGESTIONS_TOOL],
        tool_choice=TOOL_CHOICE,
        messages=[{"role": "user", "content": user_message}],
    )


@sync_to_async
def _get_machines_for_prompt() -> list[dict]:
    """Get list of machines for the LLM prompt."""
    machines = MachineInstance.objects.all()
    return [{"slug": m.slug, "name": m.name} for m in machines]


def build_yaml_prompt(
    context: context_module.GatheredContext,
    machines: list[dict],
) -> str:
    """Build YAML-formatted prompt for the LLM."""
    from the_flip.apps.discord.context import ContextMessage

    lines = []

    # Machines section
    lines.append("machines:")
    for machine in machines:
        lines.append(f"  - id: {machine['slug']}")
        lines.append(f'    name: "{_escape_yaml_string(machine["name"])}"')

    # Messages section
    lines.append("")
    lines.append("messages:")

    def format_message(msg: ContextMessage, indent: int = 2) -> list[str]:
        """Format a single message as YAML lines."""
        prefix = " " * indent
        msg_lines = []

        msg_lines.append(f'{prefix}- id: "{msg.id}"')
        msg_lines.append(f'{prefix}  author: "{_escape_yaml_string(msg.author)}"')
        # author_id: Discord snowflake (e.g., "123456789012345678") or
        # flipfix/ prefixed name (e.g., "flipfix/Sarah Chen") for webhook embeds
        if msg.author_id:
            msg_lines.append(f'{prefix}  author_id: "{msg.author_id}"')
        msg_lines.append(f'{prefix}  content: "{_escape_yaml_string(msg.content)}"')
        msg_lines.append(f'{prefix}  timestamp: "{msg.timestamp}"')

        if msg.reply_to_id:
            msg_lines.append(f'{prefix}  reply_to_id: "{msg.reply_to_id}"')

        if msg.is_target:
            msg_lines.append(f"{prefix}  is_target: true")

        if msg.is_processed:
            msg_lines.append(f"{prefix}  is_processed: true")

        if msg.flipfix_record:
            msg_lines.append(f"{prefix}  flipfix_record:")
            msg_lines.append(f"{prefix}    type: {msg.flipfix_record.record_type}")
            msg_lines.append(f"{prefix}    id: {msg.flipfix_record.record_id}")
            if msg.flipfix_record.machine_id:
                msg_lines.append(f"{prefix}    machine_id: {msg.flipfix_record.machine_id}")

        if msg.thread:
            msg_lines.append(f"{prefix}  thread:")
            for thread_msg in msg.thread:
                msg_lines.extend(format_message(thread_msg, indent + 4))

        return msg_lines

    for msg in context.messages:
        lines.extend(format_message(msg))

    return "\n".join(lines)


def _escape_yaml_string(s: str) -> str:
    """Escape a string for YAML double-quoted format."""
    # Order matters: escape backslashes first to prevent double-escaping.
    # If we escaped quotes first (" -> \"), then backslashes (\ -> \\),
    # the quote escape would become \\", which is wrong.
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\r\n", "\\n")  # Windows line endings → single \n
    s = s.replace("\r", "\\n")  # Bare carriage returns → \n
    s = s.replace("\n", "\\n")
    return s


# Set of valid record type values (derived from enum for validation)
VALID_RECORD_TYPES = set(RecordType)


def _validate_child_item(item: dict) -> ChildSuggestion | None:
    """Validate and parse a single child suggestion item from LLM output."""
    required = ["description", "source_message_ids", "author_id"]
    missing = [k for k in required if k not in item]
    if missing:
        logger.warning(
            "discord_llm_child_missing_required_fields",
            extra={"missing_fields": missing, "item_keys": list(item.keys())},
        )
        return None

    source_message_ids = item["source_message_ids"]
    if not isinstance(source_message_ids, list):
        logger.warning(
            "discord_llm_child_source_message_ids_not_list",
            extra={"type": type(source_message_ids).__name__},
        )
        return None
    if not source_message_ids:
        logger.warning("discord_llm_child_empty_source_message_ids", extra={})
        return None

    return ChildSuggestion(
        description=item["description"],
        source_message_ids=[str(mid) for mid in source_message_ids],
        author_id=str(item["author_id"]),
    )


def _validate_suggestion_item(item: dict) -> RecordSuggestion | None:
    """Validate and parse a single suggestion item from LLM output."""
    # Check required fields exist
    required = ["record_type", "description", "source_message_ids", "author_id"]
    missing = [k for k in required if k not in item]
    if missing:
        logger.warning(
            "discord_llm_missing_required_fields",
            extra={"missing_fields": missing, "item_keys": list(item.keys())},
        )
        return None

    if item["record_type"] not in VALID_RECORD_TYPES:
        logger.warning(
            "discord_llm_invalid_record_type",
            extra={"record_type": item["record_type"], "valid_types": list(VALID_RECORD_TYPES)},
        )
        return None

    source_message_ids = item["source_message_ids"]
    if not isinstance(source_message_ids, list):
        logger.warning(
            "discord_llm_source_message_ids_not_list",
            extra={"type": type(source_message_ids).__name__},
        )
        return None
    if not source_message_ids:
        logger.warning("discord_llm_empty_source_message_ids", extra={})
        return None

    record_type = RecordType(item["record_type"])
    # LLM uses "machine_id" but we store as "slug" internally
    slug = item.get("machine_id")
    parent_record_id = item.get("parent_record_id")

    # Validate slug requirement:
    # - problem_report always requires machine_id
    # - log_entry requires machine_id OR parent_record_id (inherits machine from parent)
    if record_type == RecordType.PROBLEM_REPORT and not slug:
        logger.warning("discord_llm_missing_machine_id", extra={"record_type": record_type})
        return None
    if record_type == RecordType.LOG_ENTRY and not slug and not parent_record_id:
        logger.warning("discord_llm_missing_machine_id", extra={"record_type": record_type})
        return None

    # Validate parent_record_id requirement for part_request_update
    if record_type == RecordType.PART_REQUEST_UPDATE and not parent_record_id:
        logger.warning("discord_llm_missing_parent_record_id", extra={"record_type": record_type})
        return None

    # Parse children if present
    children: list[ChildSuggestion] | None = None
    if "children" in item and isinstance(item["children"], list):
        children = []
        for child_item in item["children"]:
            if isinstance(child_item, dict):
                if child := _validate_child_item(child_item):
                    children.append(child)
        # Only keep children list if it has valid items
        if not children:
            children = None

    return RecordSuggestion(
        record_type=record_type,
        description=item["description"],
        source_message_ids=[str(mid) for mid in source_message_ids],
        author_id=str(item["author_id"]),
        slug=slug,
        parent_record_id=parent_record_id,
        children=children,
    )


def _parse_tool_response(response: anthropic.types.Message) -> list[RecordSuggestion]:
    """Parse the tool use response into RecordSuggestion objects."""
    for content in response.content:
        if content.type == "tool_use" and content.name == "record_suggestions":
            tool_input = content.input
            if not isinstance(tool_input, dict):
                logger.warning(
                    "discord_llm_tool_input_not_dict",
                    extra={"type": type(tool_input).__name__},
                )
                return []

            suggestions_data = tool_input.get("suggestions", [])
            if not isinstance(suggestions_data, list):
                logger.warning(
                    "discord_llm_suggestions_not_list",
                    extra={"type": type(suggestions_data).__name__},
                )
                return []

            suggestions = []
            for item in suggestions_data:
                if not isinstance(item, dict):
                    continue
                if suggestion := _validate_suggestion_item(item):
                    suggestions.append(suggestion)

            return suggestions

    logger.warning("discord_llm_no_tool_use_in_response", extra={})
    return []
