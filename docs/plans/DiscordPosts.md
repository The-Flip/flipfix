# Discord Posts via Bot

## Overview

Migrate outbound Discord notifications from webhooks to the Discord bot API. Currently, Flipfix posts events (problem reports, log entries, parts requests) to Discord via webhook URLs. This plan replaces that with Discord API calls using the bot token.

## Why Change

The current webhook system works, but we're adding a Discord bot for inbound message sync (see [DiscordBot.md](DiscordBot.md)). Consolidating to a single Discord integration provides:

 -  **Single configuration** - One bot token instead of bot token + webhook URLs
 - **Single modality** - All Discord code uses the same API/library
 - ability to do richer interaction (buttons, threads)
 - ability to resolve users dynamically

## Current Architecture

```
Signal fires (e.g., ProblemReport created)
    ↓
dispatch_webhook() queues async task
    ↓
Django Q worker runs deliver_webhooks()
    ↓
_deliver_to_endpoint() formats message and POSTs to webhook URL
```

Key files:
- [signals.py](../../the_flip/apps/discord/signals.py) - Signal handlers that trigger webhooks
- [tasks.py](../../the_flip/apps/discord/tasks.py) - Async task queue logic
- [formatters.py](../../the_flip/apps/discord/formatters.py) - Build Discord embed payloads
- [models.py](../../the_flip/apps/discord/models.py) - `WebhookEndpoint`, `WebhookEventSubscription`

## New Architecture

```
Signal fires (e.g., ProblemReport created)
    ↓
dispatch_discord_post() queues async task
    ↓
Django Q worker runs deliver_discord_post()
    ↓
Post to Discord REST API using bot token
```

**We won't use the bot process to send messages**. Discord's REST API accepts bot token authentication for sending. The persistent WebSocket connection (the running bot) is only needed for *receiving* events like context menu commands.

This means:
- Django Q worker will post directly to Discord API (via the discord.py library we already have installed)
- No inter-process communication between worker and bot
- Reuse existing retry/queue architecture

## Implementation Plan

### Phase 1: Bot-Based Posting

1. **Create `discord_http_utils.py`** - Utility module for Discord REST API calls
   ```python
   import discord

   def post_to_channel(channel_id: int, embeds: list[dict]) -> dict:
       """Post a message to a Discord channel using the bot token."""
       # Use discord.py's HTTP client
       # Return success/error status
   ```

2. **Add new task** in `tasks.py`
   ```python
   def deliver_discord_post(event_type: str, object_id: int, model_name: str):
       """Deliver event to Discord via bot API."""
       # Same logic as deliver_webhooks, but call post_to_channel
   ```

3. **Add configuration** (constance)
   - `DISCORD_CHANNEL_ID` - Channel to post notifications to
   - `POST_TO_DISCORD_ENABLED` - Master switch for outbound posts (default: off)

4. **Update signals** to dispatch to new task

### Phase 2: Feature Parity

Ensure bot posting matches webhook capabilities:

1. **Same embed formatting** - Reuse `formatters.py` (already builds embed dicts)
2. **Per-event-type toggles** - Rename `DISCORD_WEBHOOKS_*` to `DISCORD_POST_*`
3. **Error handling** - Same logging and error reporting

### Phase 3: Cleanup

Remove webhook code:

1. **Remove webhook models** - `WebhookEndpoint`, `WebhookEventSubscription`
2. **Remove webhook admin UI** - Endpoint management pages
3. **Remove webhook settings** - Old constance config
4. **Simplify signals** - Remove webhook dispatch code path

### Phase 4: Go Live

1. Test in staging
2. Submit PR
3. Deploy

## Technical Decisions

### Keep Queue Architecture

We'll keep the queue architecture for posting to Discord. The Django Q queue provides:

- Non-blocking signal handlers (web requests stay fast)
- Automatic retries on failure
- Timeout handling
- Logging and monitoring

### Use discord.py Library

We already have `discord.py==2.4.0` installed for the bot. Use it for posting too:

- `discord.Embed` - Type-safe embed building
- `discord.http.HTTPClient` - REST API calls without full bot connection
- Consistent with bot code

### Single Channel

One notification channel (configurable via `DISCORD_CHANNEL_ID`).

The webhook system supported multiple endpoints with different subscriptions, but we don't need that.

### Channel Restriction for Context Menu

The bot's "Save to Flipfix" context menu cannot be restricted to specific channels from code. Discord handles this via Server Settings → Integrations → [Bot] → Command Permissions.

We can validate in code: if `interaction.channel_id != config.DISCORD_CHANNEL_ID`, respond with an error message.

## Configuration Changes

### Add
- `DISCORD_CHANNEL_ID` - Target channel for posts and context menu
- `POST_TO_DISCORD_ENABLED` - Master switch for outbound posts (default: off)
- `PULL_FROM_DISCORD_ENABLED` - Master switch for inbound bot (default: off)

### Rename
- `DISCORD_WEBHOOKS_PROBLEM_REPORTS` → `DISCORD_POST_PROBLEM_REPORTS`
- `DISCORD_WEBHOOKS_LOG_ENTRIES` → `DISCORD_POST_LOG_ENTRIES`
- `DISCORD_WEBHOOKS_PARTS` → `DISCORD_POST_PARTS`

### Keep
- `DISCORD_BOT_TOKEN` - Already exists for bot
- `DISCORD_GUILD_ID` - Already exists for bot

### Remove (Phase 3)
- `DISCORD_WEBHOOKS_ENABLED` - Replaced by `POST_TO_DISCORD_ENABLED`
- `DISCORD_BOT_ENABLED` - Replaced by `PULL_FROM_DISCORD_ENABLED`
- `WebhookEndpoint` model and admin
- `WebhookEventSubscription` model and admin
