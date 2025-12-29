"""Test fixtures for LLM prompt evaluation.

This module provides test cases for evaluating the Discord bot's
LLM classifier. Each fixture includes:
- Messages representing a Discord conversation
- Expected suggestions the LLM should produce

These fixtures are used by the eval_llm_prompt management command to test
prompt changes without modifying production code.

To add a new fixture, simply define a new module-level LLMTestCase variable.
It will be automatically discovered and included in ALL_FIXTURES.

Test Users:
    User.visitor1, User.visitor2 - Museum visitors
    User.maintainer1 through User.maintainer5 - Maintenance team members
"""

from __future__ import annotations

from the_flip.apps.discord.context import FlipfixRecord
from the_flip.apps.discord.llm import RecordType
from the_flip.apps.discord.llm_eval_types import (
    ExpectedChild,
    ExpectedSuggestion,
    LLMTestCase,
    Machine,
    User,
    _msg,
)

# =============================================================================
# Multi-item fixtures
# =============================================================================

multi_item_todo_list1 = LLMTestCase(
    description="TODO list with multiple machines needing work #1",
    category="multi-item",
    messages=[
        _msg(
            User.maintainer1,
            """Here's a couple of things people could work on today:
 - Clean the playing surface of Godzilla
 - Replace the right front LRF on Hulk
 - Lubricate the flippers of Gorgar
 - Somehow get that chewing gum out of the coin slot of Baseball""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.godzilla.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.hulk.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.gorgar.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.baseball.slug),
    ],
)

multi_item_todo_list2 = LLMTestCase(
    description="TODO list with multiple machines needing work #2",
    category="multi-item",
    messages=[
        _msg(
            User.maintainer1,
            """Hey, all! Some things that you could work on tomorrow:
* Star Trek is close to playable! We can't finish it until the capacitors arrive, but we can get close! The backglass is wrapped up in padding. The adjustable feet are pretty rusty, so they may need cleaning or replacement.
* Trade Winds is also close. The only things I know that it needs: 1) the kickout at the bottom, 2) getting the score motor working properly, 3) figuring out what kind of glass it needs.
* Star Trip's left flipper coil melted. The replacement is behind the metal door at the bottom, along with the manual. It would be good to see if we can figure out why it stuck on.
* Hyperball failed during the open house. The ball lift stopped working.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.star_trek.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.trade_winds.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.star_trip.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.hyperball.slug),
    ],
)

multi_item_completed_work = LLMTestCase(
    description="Multiple machines fixed in one session - all should be log_entry",
    category="multi-item",
    messages=[
        _msg(
            User.maintainer1,
            """Did some work today:
- Fixed the left flipper on Gorgar, coil was loose
- Replaced the burnt out bulb in Blackout's backbox
- Cleaned and waxed Baseball's playfield""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.gorgar.slug),
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.blackout.slug),
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.baseball.slug),
    ],
)

multi_item_mixed_types = LLMTestCase(
    description="Message with completed work AND future work items",
    category="multi-item",
    messages=[
        _msg(
            User.maintainer1,
            """Fixed the drop target on Derby Day - the return spring was broken.
Also noticed Ballyhoo needs new flippers, the rubber is shot.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.derby_day.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.ballyhoo.slug),
    ],
)

# =============================================================================
# Work detection fixtures
# =============================================================================

work_to_be_done_needs_attention = LLMTestCase(
    description="Machine needs work - should be problem_report not log_entry",
    category="work-detection",
    messages=[
        _msg(User.maintainer1, "Gorgar needs the left flipper adjusted, it's weak", target=True),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.gorgar.slug),
    ],
)

work_to_be_done_should_be_checked = LLMTestCase(
    description="Something should be checked - problem_report",
    category="work-detection",
    messages=[
        _msg(
            User.visitor1,
            "The ball keeps getting stuck in the pop bumper area on Blackout",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.blackout.slug),
    ],
)

work_to_be_done_noticed_issue = LLMTestCase(
    description="Noticed an issue that needs fixing - problem_report",
    category="work-detection",
    messages=[
        _msg(
            User.maintainer1,
            "Noticed the display on Eight Ball Deluxe is flickering",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.eight_ball.slug),
    ],
)

completed_work_simple_fix = LLMTestCase(
    description="Simple past-tense fix - log_entry",
    category="work-detection",
    messages=[
        _msg(User.maintainer1, "Fixed the stuck ball gate on Hyperball", target=True),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.hyperball.slug),
    ],
)

completed_work_with_details = LLMTestCase(
    description="Detailed repair description - log_entry",
    category="work-detection",
    messages=[
        _msg(
            User.maintainer1,
            """Replaced the flipper coil on Hokus Pokus.
The old one was cracked. Used a FL-11630 from the parts bin.""",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.hokus_pokus.slug),
    ],
)

completed_work_thread_context = LLMTestCase(
    description="Context from earlier message clarifies work was completed",
    category="work-detection",
    messages=[
        _msg(User.visitor1, "The right flipper on Carom is dead"),
        _msg(User.maintainer1, "I'll take a look"),
        _msg(User.maintainer1, "Fixed it - the EOS switch was bent", target=True),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.carom.slug),
    ],
)

# =============================================================================
# Parts fixtures
# =============================================================================

parts_needed_explicit = LLMTestCase(
    description="Explicit parts order request",
    category="parts",
    messages=[
        _msg(
            User.maintainer1,
            "Need to order a new plunger spring for Mo Ball Deluxe",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PART_REQUEST, Machine.mo_ball.slug),
    ],
)

parts_needed_out_of_stock = LLMTestCase(
    description="Part needed but not in stock, then ordered",
    category="parts",
    messages=[
        _msg(
            User.maintainer1,
            "Ballyhoo needs a new rollover switch, we don't have any in the parts cabinet",
        ),
        _msg(
            User.maintainer2,
            "Did you check the bins in the back room?",
        ),
        _msg(
            User.maintainer1,
            "Yeah, still no luck.",
        ),
        _msg(
            User.maintainer3,
            "Who's coming in tomorrow?",
        ),
        _msg(
            User.maintainer4,
            "Me!",
        ),
        _msg(
            User.maintainer5,
            "Me too!",
        ),
        _msg(
            User.maintainer2,
            "Do we need to order one?",
        ),
        _msg(
            User.maintainer1,
            "Yup",
        ),
        _msg(
            User.maintainer2,
            "Ordered",
            target=True,
        ),
    ],
    expected=[
        # Part request with child for the order update
        ExpectedSuggestion(
            RecordType.PART_REQUEST, Machine.ballyhoo.slug, children=[ExpectedChild()]
        ),
    ],
)

# =============================================================================
# No-action fixtures
# =============================================================================

no_maintenance_social = LLMTestCase(
    description="Social chat, no maintenance content",
    category="no-action",
    messages=[
        _msg(User.maintainer1, "Hey everyone, who's coming to the meetup Saturday?", target=True),
    ],
    expected=[],
)

no_maintenance_question = LLMTestCase(
    description="Question about a machine, not reporting a problem",
    category="no-action",
    messages=[
        _msg(User.visitor1, "What year is the Gorgar machine from?", target=True),
    ],
    expected=[],
)

no_maintenance_appreciation = LLMTestCase(
    description="Appreciation message, no action needed",
    category="no-action",
    messages=[
        _msg(
            User.visitor1,
            "Just played Derby Day for the first time, what a great game!",
            target=True,
        ),
    ],
    expected=[],
)

# =============================================================================
# Context fixtures
# =============================================================================

context_problem_already_fixed = LLMTestCase(
    description="Problem reported by one user, fixed by another - target is the fix",
    category="context",
    messages=[
        _msg(User.visitor1, "Baseball's left flipper won't flip"),
        _msg(User.maintainer1, "On it"),
        _msg(User.maintainer1, "All fixed, the fuse had blown", target=True),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.baseball.slug),
    ],
)

context_still_broken = LLMTestCase(
    description="Attempted fix didn't work - should be problem_report",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "Tried fixing the pop bumper on Blackout but it's still not working",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.blackout.slug),
    ],
)

context_noisy_conversation = LLMTestCase(
    description="Fix confirmed amid off-topic chatter - should ignore noise",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "Hey Godzilla's right flipper is loose. Do we have any hex drivers to tighten?",
        ),
        _msg(
            User.maintainer2,
            "Yeah, I think the hex drivers are in the bottom drawer of the workshop's filing cabinet.",
        ),
        _msg(User.maintainer1, "Yo guys, pizza's here!"),
        _msg(User.maintainer1, "Ok, the hex driver did it."),
        _msg(
            User.maintainer1,
            "Flipper is nice and tight!",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.godzilla.slug),
    ],
)

context_reply_chain_fix = LLMTestCase(
    description="Reply chain: question answered, problem solved",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "I can't find replacement bulbs. Do we have them?",
        ),
        _msg(
            User.maintainer2,
            "Light bulbs? Electronics board, lower left corner, in bins.",
            target=True,
        ),
    ],
    expected=[],  # Just answering a question, no maintenance record needed
)

context_parts_arrival = LLMTestCase(
    description="Parts order arrived - should be log_entry documenting receipt",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "The Marco order with the capacitors and diodes for Star Trek arrived, "
            "probably in the mailroom.",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.star_trek.slug),
    ],
)

context_investigation_ongoing = LLMTestCase(
    description="Investigation in progress, problem not yet solved - problem_report",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "I still haven't found the problem with Star Trek, but I have confirmed "
            "that it's a problem with the 43V line, which is for solenoids, and the "
            "problem is somewhere in the main cabinet.",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.star_trek.slug),
    ],
)

context_noisy_conversation2 = LLMTestCase(
    description="Multi-day troubleshooting with social messages - focus on fix",
    category="context",
    messages=[
        _msg(
            User.maintainer1,
            "The kickback on Getaway wasn't working. In test mode, over half the "
            "solenoids weren't firing. Checked the fuses and 1 was blown.",
        ),
        _msg(
            User.maintainer2,
            "Oh wow! It was good until recently. Was the blown one too low?",
        ),
        _msg(
            User.maintainer1,
            "Just checked. They were all too high (except two). One was even 10A "
            "where it should have been 3!",
        ),
        _msg(
            User.maintainer3,
            "Anyone want pizza? I'm ordering.",
        ),
        _msg(
            User.maintainer1,
            "Stuffs working again with the new fuse, except for one solenoid with "
            "the diverter. That'll have to be for next time.",
            target=True,
        ),
    ],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.getaway.slug),
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.getaway.slug),
    ],
)

# =============================================================================
# Nested children fixtures
# =============================================================================

nested_unresolved_problem_with_work_attempts = LLMTestCase(
    description="Unresolved problem with multiple work attempts - problem_report with log_entry children",
    category="nested",
    messages=[
        _msg(
            User.maintainer1,
            "Gorgar's left flipper is weak",
        ),
        _msg(
            User.maintainer1,
            "Adjusted the EOS switch, flipper still weak",
        ),
        _msg(
            User.maintainer1,
            "Maybe needs a new coil",
            target=True,
        ),
    ],
    expected=[
        # Problem report with 2 log_entry children (EOS adjustment + coil observation)
        ExpectedSuggestion(
            RecordType.PROBLEM_REPORT,
            Machine.gorgar.slug,
            children=[ExpectedChild(), ExpectedChild()],
        ),
    ],
)

nested_part_request_with_updates = LLMTestCase(
    description="Part request with status updates - part_request with part_request_update children",
    category="nested",
    messages=[
        _msg(
            User.maintainer1,
            "Ballyhoo needs a new rollover switch, we're out of stock",
        ),
        _msg(
            User.maintainer2,
            "Ordered from Marco!",
        ),
        _msg(
            User.maintainer2,
            "Parts arrived today",
            target=True,
        ),
    ],
    expected=[
        # Part request with 2 update children (ordered + arrived)
        ExpectedSuggestion(
            RecordType.PART_REQUEST,
            Machine.ballyhoo.slug,
            children=[ExpectedChild(), ExpectedChild()],
        ),
    ],
)

consolidated_conversation_single_record = LLMTestCase(
    description="Back-and-forth Q&A that forms one logical unit - single log_entry",
    category="nested",
    messages=[
        _msg(
            User.maintainer1,
            "Maybe Godzilla needs a new coil",
        ),
        _msg(
            User.maintainer2,
            "Where are the coils?",
        ),
        _msg(
            User.maintainer1,
            "In the parts bin",
        ),
        _msg(
            User.maintainer1,
            "Replaced the coil but that didn't help",
            target=True,
        ),
    ],
    expected=[
        # Single log entry consolidating the whole exchange
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.godzilla.slug),
    ],
)

consolidated_troubleshooting_thread = LLMTestCase(
    description="Multi-message troubleshooting that should consolidate into one fix",
    category="nested",
    messages=[
        _msg(
            User.maintainer1,
            "Star Trek's pop bumper isn't firing",
        ),
        _msg(
            User.maintainer2,
            "Check the fuse?",
        ),
        _msg(
            User.maintainer1,
            "Fuse looks good",
        ),
        _msg(
            User.maintainer2,
            "What about the coil?",
        ),
        _msg(
            User.maintainer1,
            "Yep! Coil was disconnected. Plugged it back in, working now!",
            target=True,
        ),
    ],
    expected=[
        # Single log entry - problem was resolved, consolidate the whole troubleshooting
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.star_trek.slug),
    ],
)

# =============================================================================
# Thread fixtures
# =============================================================================

# Build thread messages with explicit message references for attribution testing
_thread_starter_msg = _msg(
    User.maintainer1,
    "Found a broken drop target on Derby Day",
)
_thread_reply1_msg = _msg(
    User.maintainer2,
    "I can take a look at it",
)
_thread_reply2_msg = _msg(
    User.maintainer2,
    "Fixed it - the return spring was broken",
    target=True,
)
# Add the children to the thread starter
_thread_starter_msg.thread = [_thread_reply1_msg, _thread_reply2_msg]

thread_fix_in_thread = LLMTestCase(
    description="Thread where problem is reported and fixed - tests thread nesting",
    category="thread",
    messages=[_thread_starter_msg],
    expected=[
        # Single log entry since problem was resolved in thread
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.derby_day.slug),
    ],
)

# Thread with preroll messages
_preroll_msg1 = _msg(
    User.maintainer3,
    "Anyone working on machines today?",
)
_preroll_msg2 = _msg(
    User.maintainer1,
    "Yes, heading to the museum now",
)
_thread_starter_msg2 = _msg(
    User.maintainer1,
    "Gorgar's left flipper seems weak",
)
_thread_reply_msg2 = _msg(
    User.maintainer2,
    "Probably needs the EOS switch adjusted",
    target=True,
)
_thread_starter_msg2.thread = [_thread_reply_msg2]

thread_with_preroll = LLMTestCase(
    description="Thread with preroll messages before it - tests context gathering",
    category="thread",
    messages=[_preroll_msg1, _preroll_msg2, _thread_starter_msg2],
    expected=[
        # Problem report since issue is not resolved
        ExpectedSuggestion(RecordType.PROBLEM_REPORT, Machine.gorgar.slug),
    ],
)


# =============================================================================
# Reply chain fixtures
# =============================================================================

# Reply chain where we can test reply_to_id
_original_msg = _msg(
    User.visitor1,
    "The right flipper on Carom isn't working",
)
_reply_msg = _msg(
    User.maintainer1,
    "I'll check it out",
    reply_to_id=_original_msg.id,
)
_fix_msg = _msg(
    User.maintainer1,
    "All fixed - the coil connector was loose",
    reply_to_id=_original_msg.id,
    target=True,
)

reply_chain_fix = LLMTestCase(
    description="Reply chain: visitor reports issue, maintainer fixes it",
    category="reply-chain",
    messages=[_original_msg, _reply_msg, _fix_msg],
    expected=[
        ExpectedSuggestion(RecordType.LOG_ENTRY, Machine.carom.slug),
    ],
)

# Reply chain for parts
_parts_original = _msg(
    User.maintainer1,
    "We need to order a new plunger spring for Ballyhoo",
)
_parts_reply = _msg(
    User.maintainer2,
    "I'll order it from Marco",
    reply_to_id=_parts_original.id,
)
_parts_ordered = _msg(
    User.maintainer2,
    "Ordered!",
    reply_to_id=_parts_original.id,
    target=True,
)

reply_chain_parts = LLMTestCase(
    description="Reply chain for part request with order confirmation",
    category="reply-chain",
    messages=[_parts_original, _parts_reply, _parts_ordered],
    expected=[
        # Part request with child for the order update
        ExpectedSuggestion(
            RecordType.PART_REQUEST,
            Machine.ballyhoo.slug,
            children=[ExpectedChild()],
        ),
    ],
)


# =============================================================================
# Webhook/parent linking fixtures
# =============================================================================

# Webhook embed that represents an existing problem report
_webhook_problem_report = _msg(
    "Flipfix",  # Webhook uses string, not TestUser
    "Left flipper is weak on Gorgar",
    author_id=None,  # Webhook messages don't have author_id
    flipfix_record=FlipfixRecord(
        record_type=RecordType.PROBLEM_REPORT,
        record_id=42,
        machine_id=Machine.gorgar.slug,
    ),
)
_log_reply_to_webhook = _msg(
    User.maintainer1,
    "Fixed it - adjusted the EOS switch",
    reply_to_id=_webhook_problem_report.id,
    target=True,
)

webhook_reply_creates_linked_log = LLMTestCase(
    description="Reply to webhook embed creates log_entry linked to existing problem",
    category="webhook",
    messages=[_webhook_problem_report, _log_reply_to_webhook],
    expected=[
        # Log entry should link to the existing problem report via parent_record_id
        ExpectedSuggestion(
            RecordType.LOG_ENTRY,
            Machine.gorgar.slug,
            parent_record_id=42,
        ),
    ],
)

# Webhook embed for existing part request
_webhook_part_request = _msg(
    "Flipfix",  # Webhook uses string, not TestUser
    "Need new rollover switch",
    author_id=None,
    flipfix_record=FlipfixRecord(
        record_type=RecordType.PART_REQUEST,
        record_id=99,
        machine_id=Machine.ballyhoo.slug,
    ),
)
_update_reply_to_webhook = _msg(
    User.maintainer2,
    "Parts arrived today!",
    reply_to_id=_webhook_part_request.id,
    target=True,
)

webhook_reply_creates_part_update = LLMTestCase(
    description="Reply to part request webhook creates part_request_update",
    category="webhook",
    messages=[_webhook_part_request, _update_reply_to_webhook],
    expected=[
        ExpectedSuggestion(
            RecordType.PART_REQUEST_UPDATE,
            Machine.ballyhoo.slug,
            parent_record_id=99,
        ),
    ],
)


# =============================================================================
# Attribution fixtures
# =============================================================================

# Test author_id attribution
_author_test_msg = _msg(
    User.maintainer1,
    "Fixed the pop bumper on Blackout",
    target=True,
)

author_id_attribution = LLMTestCase(
    description="Single message tests author_id attribution",
    category="attribution",
    messages=[_author_test_msg],
    expected=[
        ExpectedSuggestion(
            RecordType.LOG_ENTRY,
            Machine.blackout.slug,
            author_id=_author_test_msg.author_id,
        ),
    ],
)

# Test source_message_ids tracking
_source_msg1 = _msg(
    User.maintainer1,
    "Star Trek's kickback isn't working",
)
_source_msg2 = _msg(
    User.maintainer1,
    "Found the problem - blown fuse. Replaced it, working now!",
    target=True,
)

source_message_ids_tracking = LLMTestCase(
    description="Multiple messages consolidated should track all source_message_ids",
    category="attribution",
    messages=[_source_msg1, _source_msg2],
    expected=[
        ExpectedSuggestion(
            RecordType.LOG_ENTRY,
            Machine.star_trek.slug,
            source_message_ids=[_source_msg1.id, _source_msg2.id],
        ),
    ],
)

# Test multi-author attribution - visitor reports problem, maintainer investigates
# This tests that the problem_report is attributed to the visitor who reported it
_multi_author_problem = _msg(
    User.visitor1,
    "Godzilla's left flipper is stuck",
)
_multi_author_investigation = _msg(
    User.maintainer1,
    "Checked it - the coil is burnt out, need to order a replacement",
    target=True,
)

multi_author_attribution = LLMTestCase(
    description="Multi-author scenario - problem from visitor, investigation from maintainer",
    category="attribution",
    messages=[_multi_author_problem, _multi_author_investigation],
    expected=[
        # Problem report should be attributed to visitor who originally reported it
        # Don't assert on children - LLM may or may not create a child for the investigation
        ExpectedSuggestion(
            RecordType.PROBLEM_REPORT,
            Machine.godzilla.slug,
            author_id=_multi_author_problem.author_id,
        ),
    ],
)


# =============================================================================
# Auto-discover all fixtures
# =============================================================================

ALL_FIXTURES: dict[str, LLMTestCase] = {
    name: obj for name, obj in globals().items() if isinstance(obj, LLMTestCase)
}
