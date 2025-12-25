"""LLM integration for Discord bot message analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic
from anthropic.types import ToolChoiceToolParam, ToolParam
from asgiref.sync import sync_to_async
from constance import config

from the_flip.apps.catalog.models import MachineInstance

logger = logging.getLogger(__name__)


@dataclass
class RecordSuggestion:
    """A suggested record to create from Discord messages."""

    record_type: str  # "log_entry", "problem_report", "part_request"
    machine_slug: str
    machine_name: str
    description: str
    selected: bool = True


@dataclass
class MessageContext:
    """Context gathered from Discord messages."""

    messages: list[dict]  # [{author, content, timestamp}, ...]
    target_message_id: int
    flipfix_urls: list[str]


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


SYSTEM_PROMPT = """You are analyzing a Discord message from a pinball museum's maintenance channel.
Your job is to identify what maintenance records should be created in Flipfix (the maintenance tracking system).

IMPORTANT: Only analyze the TARGET MESSAGE (marked with **). The surrounding messages are provided
only for context to help you understand the conversation. Do NOT create records for other messages.

Record types:
- log_entry: Work that was done on a machine (repairs, adjustments, cleaning)
- problem_report: A problem that needs attention (something broken, not working right)
- part_request: Parts that need to be ordered

Guidelines:
- ONLY suggest records for the target message, not for context messages
- Match machine names to the provided list (use the slug for machine_slug, display name for machine_name)
- If the target message mentions multiple machines, create separate suggestions for each
- Use context to understand if a problem was already fixed (then suggest log_entry, not problem_report)
- If the target message has no maintenance-related content, call the tool with an empty suggestions array

Description guidelines - BE VERBOSE AND FAITHFUL:
- Preserve the original wording from relevant messages as much as possible
- Include ALL specific details: part names, symptoms, what was tried, what worked
- When context messages add important details, incorporate them into the description
- It's better to include too much detail than too little
- Don't summarize or paraphrase - use the actual words from the conversation
- Example: if the message thread is...
    - godzilla's right flipper is broken
    - ok I fixed it
    - the problem was the flipper pin was bent; we had a spare flipper pin, fortunately
... then the description should be something like: "Right flipper was broken. Fixed it. The problem was the flipper pin was bent; we had a spare flipper pin, fortunately."
"""

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
                            "enum": ["log_entry", "problem_report", "part_request"],
                            "description": "Type of maintenance record",
                        },
                        "machine_slug": {
                            "type": "string",
                            "description": "The slug of the machine from the provided list",
                        },
                        "machine_name": {
                            "type": "string",
                            "description": "The display name of the machine",
                        },
                        "description": {
                            "type": "string",
                            "description": "Details of the work/problem/parts needed",
                        },
                    },
                    "required": ["record_type", "machine_slug", "machine_name", "description"],
                },
            },
        },
        "required": ["suggestions"],
    },
}

TOOL_CHOICE: ToolChoiceToolParam = {"type": "tool", "name": "record_suggestions"}


async def analyze_messages(context: MessageContext) -> AnalysisResult:
    """Use Claude to analyze Discord messages and suggest records to create."""
    api_key = await _get_api_key()
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not configured")
        return AnalysisResult.failure(
            "Anthropic API key not configured. Please contact an administrator."
        )

    # Get machine list from database
    machines = await _get_machines_for_prompt()

    # Check if parts system is enabled
    parts_enabled = await _get_parts_enabled()

    # Build the user message
    user_message = _build_user_message(context, machines)

    try:
        # Run the synchronous API call in a thread
        response = await _call_anthropic(api_key, user_message)

        # Extract tool use from response
        suggestions = _parse_tool_response(response)

        # Filter out part_request suggestions if parts system is disabled
        if not parts_enabled:
            original_count = len(suggestions)
            suggestions = [s for s in suggestions if s.record_type != "part_request"]
            filtered_count = original_count - len(suggestions)
            if filtered_count > 0:
                logger.info(
                    "discord_llm_filtered_parts",
                    extra={"filtered_count": filtered_count},
                )

        logger.info(
            "discord_llm_analysis_complete",
            extra={
                "message_count": len(context.messages),
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
        logger.exception("discord_llm_error: %s", e)
        return AnalysisResult.failure("Unexpected error during analysis. Please try again.")


@sync_to_async
def _get_api_key() -> str:
    """Get Anthropic API key from Constance config."""
    return config.ANTHROPIC_API_KEY


@sync_to_async
def _get_parts_enabled() -> bool:
    """Check if parts system is enabled in Constance config."""
    return config.PARTS_ENABLED


@sync_to_async
def _call_anthropic(api_key: str, user_message: str) -> anthropic.types.Message:
    """Call Anthropic API with tool use for structured output."""
    client = anthropic.Anthropic(api_key=api_key)
    return client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[RECORD_SUGGESTIONS_TOOL],
        tool_choice=TOOL_CHOICE,
        messages=[{"role": "user", "content": user_message}],
    )


@sync_to_async
def _get_machines_for_prompt() -> list[dict]:
    """Get list of machines for the LLM prompt."""
    machines = MachineInstance.objects.all()
    return [{"slug": m.slug, "name": m.name} for m in machines]


def _build_user_message(context: MessageContext, machines: list[dict]) -> str:
    """Build the user message for the LLM."""
    parts = []

    # Machine list
    parts.append("## Available Machines")
    for machine in machines:
        parts.append(f"- {machine['name']} (slug: {machine['slug']})")

    # Flipfix URLs if any
    if context.flipfix_urls:
        parts.append("\n## Related Flipfix Records")
        for url in context.flipfix_urls:
            parts.append(f"- {url}")

    # Messages
    parts.append("\n## Discord Messages")
    parts.append(
        "(Messages are in chronological order. The user clicked on the message marked with **)"
    )
    for msg in context.messages:
        marker = "**" if msg.get("is_target") else ""
        parts.append(f"{marker}[{msg['timestamp']}] {msg['author']}: {msg['content']}{marker}")

    parts.append("\n## Task")
    parts.append(
        "Analyze ONLY the target message (marked with **) and use the record_suggestions tool to submit your suggestions. "
        "The other messages are just for context - do not create records for them."
    )

    return "\n".join(parts)


def _parse_tool_response(response: anthropic.types.Message) -> list[RecordSuggestion]:
    """Parse the tool use response into RecordSuggestion objects."""
    for content in response.content:
        if content.type == "tool_use" and content.name == "record_suggestions":
            tool_input = content.input
            if not isinstance(tool_input, dict):
                logger.warning("discord_llm_tool_input_not_dict")
                return []

            suggestions_data = tool_input.get("suggestions", [])
            if not isinstance(suggestions_data, list):
                logger.warning("discord_llm_suggestions_not_list")
                return []

            suggestions = []
            for item in suggestions_data:
                if not isinstance(item, dict):
                    continue
                if not all(
                    k in item
                    for k in ["record_type", "machine_slug", "machine_name", "description"]
                ):
                    continue
                if item["record_type"] not in ["log_entry", "problem_report", "part_request"]:
                    continue

                suggestions.append(
                    RecordSuggestion(
                        record_type=item["record_type"],
                        machine_slug=item["machine_slug"],
                        machine_name=item["machine_name"],
                        description=item["description"],
                        selected=True,
                    )
                )

            return suggestions

    logger.warning("discord_llm_no_tool_use_in_response")
    return []
