"""Types and helpers for LLM prompt evaluation.

This module provides the infrastructure for LLM eval fixtures:
- TestUser: Represents a Discord user in test fixtures
- User: Predefined test users (visitors and maintainers)
- TestMachine: Represents a pinball machine in test fixtures
- Machine: Predefined test machines
- ExpectedChild, ExpectedSuggestion, LLMTestCase: Test case structures
- _msg(): Helper to create ContextMessage instances

The actual fixtures are in llm_eval_fixtures.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from the_flip.apps.discord.context import ContextMessage, FlipfixRecord, GatheredContext


@dataclass(frozen=True)
class TestUser:
    """A Discord user for test fixtures.

    Attributes:
        display_name: The user's display name shown in Discord
        username: The user's Discord username (handle)
        user_id: Discord snowflake ID (18-digit string)
    """

    display_name: str
    username: str
    user_id: str


class User:
    """Predefined test users for fixtures.

    Use these instead of string literals:
        User.visitor1, User.visitor2 - Museum visitors
        User.maintainer1 through User.maintainer5 - Maintenance team members
    """

    visitor1 = TestUser(
        display_name="Sarah Chen",
        username="sarahc_plays",
        user_id="1001000000000000001",
    )
    visitor2 = TestUser(
        display_name="Mike Rodriguez",
        username="pinball_mike",
        user_id="1001000000000000002",
    )
    maintainer1 = TestUser(
        display_name="Bob Wilson",
        username="bob_the_fixer",
        user_id="1002000000000000001",
    )
    maintainer2 = TestUser(
        display_name="Alice Martinez",
        username="alice_m",
        user_id="1002000000000000002",
    )
    maintainer3 = TestUser(
        display_name="Tom Baker",
        username="tombaker42",
        user_id="1002000000000000003",
    )
    maintainer4 = TestUser(
        display_name="Jenny Park",
        username="jenny_fixes",
        user_id="1002000000000000004",
    )
    maintainer5 = TestUser(
        display_name="Carlos Reyes",
        username="carlos_r",
        user_id="1002000000000000005",
    )


@dataclass(frozen=True)
class TestMachine:
    """A pinball machine for test fixtures.

    Attributes:
        slug: Machine slug (used in ExpectedSuggestion and LLM output)
        name: Display name shown to the LLM in the machines list
    """

    slug: str
    name: str


class Machine:
    """Predefined test machines for fixtures.

    Use Machine.godzilla.slug in ExpectedSuggestion.
    The Machine class also provides ALL_MACHINES for building the LLM prompt.
    """

    # Machines used in fixtures (alphabetical by attribute name)
    ballyhoo = TestMachine("ballyhoo", "Ballyhoo")
    baseball = TestMachine("baseball", "Baseball")
    blackout = TestMachine("blackout", "Blackout")
    carom = TestMachine("carom", "Carom")
    derby_day = TestMachine("derby-day", "Derby Day")
    eight_ball = TestMachine(
        "eight-ball-deluxe-limited-edition", "Eight Ball Deluxe (Limited Edition)"
    )
    getaway = TestMachine("the-getaway-high-speed-ii", "The Getaway: High Speed II")
    godzilla = TestMachine("godzilla-premium", "Godzilla (Premium)")
    gorgar = TestMachine("gorgar", "Gorgar")
    hokus_pokus = TestMachine("hokus-pokus", "Hokus Pokus")
    hulk = TestMachine("the-incredible-hulk", "The Incredible Hulk")
    hyperball = TestMachine("hyperball", "Hyperball")
    mo_ball = TestMachine("mo-ball-deluxe", "Mo Ball Deluxe")
    star_trek = TestMachine("star-trek", "Star Trek")
    star_trip = TestMachine("star-trip", "Star Trip")
    trade_winds = TestMachine("trade-winds", "Trade Winds")


def get_all_test_machines() -> list[dict[str, str]]:
    """Get all test machines as a list of dicts for build_yaml_prompt().

    Auto-discovers all TestMachine instances from the Machine class.
    Returns list of {"slug": "...", "name": "..."} dicts sorted by slug.
    """
    machines = [
        {"slug": m.slug, "name": m.name}
        for m in vars(Machine).values()
        if isinstance(m, TestMachine)
    ]
    return sorted(machines, key=lambda m: m["slug"])


@dataclass
class ExpectedChild:
    """Expected child record nested under a parent suggestion.

    Children inherit record_type from parent:
    - problem_report parent -> log_entry children
    - part_request parent -> part_request_update children

    Fields are optional - only specified fields are compared.
    """

    author_id: str | None = None  # Discord user ID to attribute this record to
    source_message_ids: list[str] | None = None  # Message IDs that contributed


@dataclass
class ExpectedSuggestion:
    """Expected suggestion from LLM analysis.

    By default, only record_type and slug are compared. Description is not
    checked because exact wording varies and isn't important for correctness.

    Optional fields enable testing additional LLM capabilities:
    - children: Nested child records (count and optionally attribution)
    - parent_record_id: Linking to existing Flipfix records from context
    - author_id: Discord user attribution
    - source_message_ids: Multi-message source tracking
    """

    record_type: str
    slug: str
    children: list[ExpectedChild] | None = None  # Expected child records
    parent_record_id: int | None = None  # Expected link to existing Flipfix record
    author_id: str | None = None  # Discord user ID to attribute this record to
    source_message_ids: list[str] | None = None  # Message IDs that contributed


@dataclass
class LLMTestCase:
    """A test case for LLM prompt evaluation."""

    description: str
    messages: list[ContextMessage]
    expected: list[ExpectedSuggestion]
    category: str = ""  # Fixture category for grouped display

    def to_context(self) -> GatheredContext:
        """Convert to GatheredContext for the LLM."""
        # Find target message ID
        target_id = next((m.id for m in self.messages if m.is_target), self.messages[-1].id)
        return GatheredContext(
            messages=self.messages,
            target_message_id=target_id,
        )


# =============================================================================
# Message building helpers
# =============================================================================

# Message ID counter for generating unique IDs
_msg_id_counter = 0

# Author ID counter for generating unique Discord user IDs
_author_id_counter = 1000000000000000000  # Discord snowflake range


def _generate_timestamp(msg_number: int) -> str:
    """Generate a deterministic pseudo-random timestamp from message number.

    Uses modular arithmetic to produce varied but reproducible timestamps.
    This avoids the "00 minutes, 00 seconds" pattern that might give
    unintended signals to the LLM.

    The sequence produces timestamps like:
    - Message 1: 10:07:17
    - Message 2: 10:14:34
    - Message 3: 10:21:51
    - etc.
    """
    # Base progression: ~5 minutes per message
    base_minutes = msg_number * 5

    # Add pseudo-random jitter (0-4 minutes) based on message number
    # The multiplier 7 is coprime with 5, giving good distribution
    jitter = (msg_number * 7) % 5

    total_minutes = base_minutes + jitter

    # Convert to hours and minutes (starting from 10:00)
    hours = 10 + (total_minutes // 60)
    minutes = total_minutes % 60

    # Pseudo-random seconds (0-59) - multiplier 17 gives good spread
    seconds = (msg_number * 17) % 60

    return f"2025-01-15T{hours:02d}:{minutes:02d}:{seconds:02d}Z"


def _msg(
    author: TestUser | str,
    content: str,
    timestamp: str | None = None,
    *,
    target: bool = False,
    author_id: str | None = None,
    reply_to_id: str | None = None,
    flipfix_record: FlipfixRecord | None = None,
    children: list[ContextMessage] | None = None,
) -> ContextMessage:
    """Create a ContextMessage for fixtures.

    Args:
        author: TestUser instance or display name string (for webhook embeds)
        content: Message text
        timestamp: ISO timestamp (auto-generated if not provided)
        target: If True, marks this as the clicked message
        author_id: Discord user ID (auto from TestUser, auto-generated for strings,
                   None for webhooks)
        reply_to_id: ID of message this replies to (for reply chains)
        flipfix_record: Parsed Flipfix webhook embed data
        children: Nested thread messages (for thread starter messages)
    """
    global _msg_id_counter, _author_id_counter
    _msg_id_counter += 1

    # Auto-generate timestamp if not provided
    resolved_timestamp = (
        timestamp if timestamp is not None else _generate_timestamp(_msg_id_counter)
    )

    # Resolve author name and ID based on author type
    resolved_author_id: str | None
    if isinstance(author, TestUser):
        author_name = author.display_name
        resolved_author_id = author_id if author_id is not None else author.user_id
    else:
        # String author - for webhook embeds or backward compatibility
        author_name = author
        if author_id is not None:
            # Explicitly provided author_id
            resolved_author_id = author_id
        elif flipfix_record is not None:
            # Webhook embeds use flipfix/ prefix for name-based author lookup
            resolved_author_id = f"flipfix/{author_name}"
        else:
            # Generate a unique author_id based on author name for consistency
            # This ensures same author name gets same ID across messages
            resolved_author_id = str(_author_id_counter + hash(author) % 1000000)

    return ContextMessage(
        id=str(_msg_id_counter),
        author=author_name,
        author_id=resolved_author_id,
        content=content,
        timestamp=resolved_timestamp,
        is_target=target,
        reply_to_id=reply_to_id,
        flipfix_record=flipfix_record,
        thread=children or [],
    )
