# Discord Bot

## Overview

A Discord Bot that syncs messages from The Flip's workshop channel to Flipfix.

This doc is about replacing the first attempt at a Discord Bot that used keyword-based auto-classification  with a human-initiated, LLM-assisted approach using Discord's context menu commands.

## Why the Change

The keyword-based classifier has fundamental limitations with natural conversation:

1. **Multi-machine messages** - One message mentions multiple machines
2. **Self-resolving threads** - "Need parts" → "Found them" shouldn't create records
3. **Multi-item lists** - Shopping lists with many items to order
4. **Extended discussions** - Parts ordering spanning multiple days/messages
5. **Mixed content** - Relevant + irrelevant info in same message
6. **Classification ambiguity** - Is it a problem report, log entry, or parts request?

These issues can't be solved with better keywords—they require understanding context and human judgment.

## New Architecture

### Interaction Flow

```
User right-clicks any message → "📋 Record to Flipfix"
    ↓
Bot gathers context:
  - The clicked message
  - Surrounding messages (configurable window of time)
  - Thread context, if in a thread
  - Any Flipfix URLs found in embeds (webhook posts)
    ↓
LLM analyzes and returns structured suggestions:
  - Suggested record type(s)
  - Which machine(s)
  - Suggested description (summarized from messages)
  - Related Flipfix records (from URLs found)
    ↓
Ephemeral response with checkboxes:
  ☑ Create Log Entry for "Godzilla" - "Fixed flipper..."
  ☐ Create Part Request for "Star Trek" - "Need coil..."
  [Confirm] [Cancel]
    ↓
User confirms → Records created
    ↓
Ephemeral response updated with links to created records
```

### Key Design Decisions

1. **No `on_message` handler** - Bot only responds to context menu interactions
2. **Human-initiated** - User decides what's worth recording
3. **LLM for understanding** - Natural language comprehension, not keywords
4. **Ephemeral confirmation** - User reviews and edits before creating records
5. **Context-aware** - Gathers surrounding messages and thread context
6. **Webhook URL extraction** - Finds related Flipfix records from webhook embeds

### What We Keep

- `DiscordUserLink` - Map Discord users to maintainers
- `DiscordMessageMapping` - Prevent duplicate processing
- `parsers/references.py` - `parse_url()` extracts Flipfix record references
- `signals.py`, `tasks.py`, `formatters.py` - Outbound notification system

### What We Remove/Replace

- `parsers/core.py` - Keyword classifier (replaced by LLM)
- `parsers/intent.py` - Keyword detection
- `parsers/machines.py` - Machine name matching (LLM handles this)
- `bot.py` `on_message` handler - No longer needed

## Implementation Components

### 1. Context Menu Command

```python
@bot.tree.context_menu(name="📋 Record to Flipfix")
async def record_to_flipfix(interaction: discord.Interaction, message: discord.Message):
    # Defer with ephemeral response (only user sees it)
    await interaction.response.defer(ephemeral=True)

    # Gather context
    context = await gather_message_context(message)

    # Call LLM for analysis
    suggestions = await analyze_with_llm(context)

    # Show confirmation UI
    view = RecordConfirmationView(suggestions)
    await interaction.followup.send(embed=suggestions_embed, view=view, ephemeral=True)
```

### 2. Context Gathering

```python
async def gather_message_context(message: discord.Message) -> MessageContext:
    """Gather context around the clicked message."""
    context = MessageContext(
        target_message=message,
        surrounding_messages=[],
        flipfix_references=[],
    )

    # Get surrounding messages
    async for msg in message.channel.history(limit=10, around=message):
        context.surrounding_messages.append(msg)

        # Extract Flipfix URLs from embeds
        for embed in msg.embeds:
            if embed.url and "theflip.app" in embed.url:
                ref = parse_url(embed.url)
                if ref:
                    context.flipfix_references.append(ref)

    return context
```

### 3. LLM Analysis

```python
async def analyze_with_llm(context: MessageContext) -> list[RecordSuggestion]:
    """Use LLM to analyze messages and suggest records to create."""

    # Build prompt with:
    # - List of machines in the system
    # - Message content and context
    # - Any related Flipfix records found
    # - Instructions for structured output

    # Returns list of suggestions like:
    # [
    #     RecordSuggestion(
    #         record_type=RecordType.LOG_ENTRY,
    #         machine_slug="godzilla",
    #         description="Fixed flipper coil that was sticking",
    #         related_problem_report_id=42,  # From webhook URL
    #         source_message_ids=[123, 124, 125],
    #     ),
    #     ...
    # ]
```

### 4. Confirmation UI

Discord components for the ephemeral response:
- Embed showing suggested records
- Checkboxes (Select menu) to choose which to create
- Confirm/Cancel buttons
- Optional: Edit button to modify descriptions

## Configuration

New settings (via constance or environment):
- `DISCORD_LLM_MODEL` - Which model to use for analysis
- `DISCORD_CONTEXT_WINDOW` - How many messages to gather (default: 10)
- `DISCORD_BOT_ENABLED` - Keep existing toggle

## Implementation Phases

### Phase 1: UI Prototype (No LLM, No Record Creation)

Goal: Get the Discord interaction working end-to-end as fast as possible.

- Context menu command "📋 Record to Flipfix" appears on messages
- Gathers surrounding messages and displays them in ephemeral response
- Shows mock suggestions with hardcoded/placeholder data
- Confirm button shows "success" message with link to Flipfix home page
- No LLM calls, no database writes

### Phase 2: LLM Integration

- Replace mock suggestions with real LLM analysis
- Build prompt with machine list, message context, Flipfix URLs
- Parse structured output into suggestions

### Phase 3: Record Creation

- Wire up Confirm button to actually create records in Flipfix
- Show real links to created records
- Handle errors gracefully

### Phase 4: Polish & Cleanup

- Remove old keyword classifier code
- Add rate limiting for LLM calls
- Handle edge cases (no suggestions, LLM errors, etc.)

## Open Questions

- [ ] Which LLM provider/model? (Claude, OpenAI, local?)
- [ ] How to handle images/attachments in context?
- [ ] Rate limiting for LLM calls?
- [ ] Should we limit context menu to specific channels?
