"""Test fixtures for LLM prompt evaluation.

This module provides curated test cases for evaluating the Discord bot's
LLM classifier. Each fixture includes:
- Messages representing a Discord conversation
- Expected suggestions the LLM should produce

These fixtures are used by the eval_llm_prompt management command to test
prompt changes without modifying production code.

To add a new fixture, simply define a new module-level LLMTestCase variable.
It will be automatically discovered and included in ALL_FIXTURES.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from the_flip.apps.discord.llm import MessageContext


@dataclass
class ExpectedSuggestion:
    """Expected suggestion from LLM analysis.

    Only record_type and machine_slug are compared. Description is not
    checked because exact wording varies and isn't important for correctness.
    """

    record_type: str  # "log_entry", "problem_report", "part_request"
    machine_slug: str


@dataclass
class LLMTestCase:
    """A test case for LLM prompt evaluation."""

    description: str
    messages: list[dict]
    expected: list[ExpectedSuggestion]
    flipfix_urls: list[str] = field(default_factory=list)

    def to_context(self) -> MessageContext:
        """Convert to MessageContext for the LLM."""
        return MessageContext(
            messages=self.messages,
            target_message_id=0,  # Not used by LLM logic
            flipfix_urls=self.flipfix_urls,
        )


def _msg(
    author: str,
    content: str,
    timestamp: str = "2025-01-15 10:00",
    *,
    target: bool = False,
) -> dict:
    """Create a message dict for fixtures."""
    return {
        "author": author,
        "content": content,
        "timestamp": timestamp,
        "is_target": target,
    }


# =============================================================================
# Fixtures
# =============================================================================

multi_item_todo_list1 = LLMTestCase(
    description="TODO list with multiple machines needing work #1",
    messages=[
        _msg(
            "maintainer1",
            """Here's a couple of things people could work on today:
 - Clean the playing surface of Godzilla
 - Replace the right front LRF on Hulk
 - Lubricate the flippers of Gorgar
 - Somehow get that chewing gum out of the coin slot of Baseball""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "godzilla-premium"),
        ExpectedSuggestion("problem_report", "the-incredible-hulk"),
        ExpectedSuggestion("problem_report", "gorgar"),
        ExpectedSuggestion("problem_report", "baseball"),
    ],
)

multi_item_todo_list2 = LLMTestCase(
    description="TODO list with multiple machines needing work #2",
    messages=[
        _msg(
            "maintainer1",
            """Hey, all! Some things that you could work on tomorrow:
* Star Trek is close to playable! We can't finish it until the capacitors arrive, but we can get close! The backglass is wrapped up in padding. The adjustable feet are pretty rusty, so they may need cleaning or replacement.
* Trade Winds is also close. The only things I know that it needs: 1) the kickout at the bottom, 2) getting the score motor working properly, 3) figuring out what kind of glass it needs.
* Star Trip's left flipper coil melted. The replacement is behind the metal door at the bottom, along with the manual. It would be good to see if we can figure out why it stuck on.
* Hyperball failed during the open house. The ball lift stopped working.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "star-trek"),
        ExpectedSuggestion("problem_report", "trade-winds"),
        ExpectedSuggestion("problem_report", "star-trip"),
        ExpectedSuggestion("problem_report", "hyperball"),
    ],
)

multi_item_completed_work = LLMTestCase(
    description="Multiple machines fixed in one session - all should be log_entry",
    messages=[
        _msg(
            "maintainer1",
            """Did some work today:
- Fixed the left flipper on Gorgar, coil was loose
- Replaced the burnt out bulb in Blackout's backbox
- Cleaned and waxed Baseball's playfield""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "gorgar"),
        ExpectedSuggestion("log_entry", "blackout"),
        ExpectedSuggestion("log_entry", "baseball"),
    ],
)

multi_item_mixed_types = LLMTestCase(
    description="Message with completed work AND future work items",
    messages=[
        _msg(
            "maintainer1",
            """Fixed the drop target on Derby Day - the return spring was broken.
Also noticed Ballyhoo needs new flippers, the rubber is shot.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "derby-day"),
        ExpectedSuggestion("problem_report", "ballyhoo"),
    ],
)

work_to_be_done_needs_attention = LLMTestCase(
    description="Machine needs work - should be problem_report not log_entry",
    messages=[
        _msg("maintainer1", "Gorgar needs the left flipper adjusted, it's weak", target=True),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "gorgar"),
    ],
)

work_to_be_done_should_be_checked = LLMTestCase(
    description="Something should be checked - problem_report",
    messages=[
        _msg(
            "visitor1",
            "The ball keeps getting stuck in the pop bumper area on Blackout",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "blackout"),
    ],
)

work_to_be_done_noticed_issue = LLMTestCase(
    description="Noticed an issue that needs fixing - problem_report",
    messages=[
        _msg(
            "maintainer1",
            "Noticed the display on Eight Ball Deluxe is flickering",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "eight-ball-deluxe-limited-edition"),
    ],
)

completed_work_simple_fix = LLMTestCase(
    description="Simple past-tense fix - log_entry",
    messages=[
        _msg("maintainer1", "Fixed the stuck ball gate on Hyperball", target=True),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "hyperball"),
    ],
)

completed_work_with_details = LLMTestCase(
    description="Detailed repair description - log_entry",
    messages=[
        _msg(
            "maintainer1",
            """Replaced the flipper coil on Hokus Pokus.
The old one was cracked. Used a FL-11630 from the parts bin.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "hokus-pokus"),
    ],
)

completed_work_thread_context = LLMTestCase(
    description="Context from earlier message clarifies work was completed",
    messages=[
        _msg("visitor1", "The right flipper on Carom is dead", "2025-01-15 09:00"),
        _msg("maintainer1", "I'll take a look", "2025-01-15 09:30"),
        _msg("maintainer1", "Fixed it - the EOS switch was bent", "2025-01-15 10:00", target=True),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "carom"),
    ],
)

parts_needed_explicit = LLMTestCase(
    description="Explicit parts order request",
    messages=[
        _msg(
            "maintainer1",
            "Need to order a new plunger spring for Mo Ball Deluxe",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("part_request", "mo-ball-deluxe"),
    ],
)

parts_needed_out_of_stock = LLMTestCase(
    description="Part needed but not in stock",
    messages=[
        _msg(
            "maintainer1",
            "Ballyhoo needs a new rollover switch, we don't have any in the parts cabinet",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("part_request", "ballyhoo"),
    ],
)

no_maintenance_social = LLMTestCase(
    description="Social chat, no maintenance content",
    messages=[
        _msg("maintainer1", "Hey everyone, who's coming to the meetup Saturday?", target=True),
    ],
    expected=[],
)

no_maintenance_question = LLMTestCase(
    description="Question about a machine, not reporting a problem",
    messages=[
        _msg("visitor1", "What year is the Gorgar machine from?", target=True),
    ],
    expected=[],
)

no_maintenance_appreciation = LLMTestCase(
    description="Appreciation message, no action needed",
    messages=[
        _msg(
            "visitor1",
            "Just played Derby Day for the first time, what a great game!",
            target=True,
        ),
    ],
    expected=[],
)

context_problem_already_fixed = LLMTestCase(
    description="Problem reported by one user, fixed by another - target is the fix",
    messages=[
        _msg("visitor1", "Baseball's left flipper won't flip", "2025-01-15 09:00"),
        _msg("maintainer1", "On it", "2025-01-15 09:15"),
        _msg("maintainer1", "All fixed, the fuse had blown", "2025-01-15 09:45", target=True),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "baseball"),
    ],
)

context_still_broken = LLMTestCase(
    description="Attempted fix didn't work - should be problem_report",
    messages=[
        _msg(
            "maintainer1",
            "Tried fixing the pop bumper on Blackout but it's still not working",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("problem_report", "blackout"),
    ],
)

context_noisy_conversation = LLMTestCase(
    description="Fix confirmed amid off-topic chatter - should ignore noise",
    messages=[
        _msg(
            "maintainer1",
            "Hey Godzilla's right flipper is loose. Do we have any hex drivers to tighten?",
            "2025-01-15 14:00",
        ),
        _msg(
            "maintainer2",
            "Yeah, I think the hex drivers are in the bottom drawer of the workshop's filing cabinet.",
            "2025-01-15 14:05",
        ),
        _msg("maintainer1", "Yo guys, pizza's here!", "2025-01-15 14:30"),
        _msg("maintainer1", "Ok, the hex driver did it.", "2025-01-15 15:00"),
        _msg(
            "maintainer1",
            "Flipper is nice and tight!",
            "2025-01-15 15:01",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion("log_entry", "godzilla-premium"),
    ],
)

# =============================================================================
# Auto-discover all fixtures
# =============================================================================

ALL_FIXTURES: dict[str, LLMTestCase] = {
    name: obj for name, obj in globals().items() if isinstance(obj, LLMTestCase)
}
