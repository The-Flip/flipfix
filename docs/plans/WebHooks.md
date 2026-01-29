# Webhooks Feature Requirements

## Overview

We want to enable maintainers to stay informed about machine issues and maintenance work without constantly checking the web app, but instead recieving notifications about events from the app (such as problem reports and work log entries) in their preferred channels, most principally the museum's existing Discord server. However, we'd also like to support other channels like Slack and email.

## The Basic Architectural Idea

Enable superadmins to configure web hooks for external services. There are ways to configure web hooks for Discord, Slack, email, etc.

## Goals

1. **Notify maintainers in real time** when activity happens
2. **Support multiple webhook destinations per event** (different Discord channels, Slack, email services)
3. **Allow granular control** over which events trigger which webhooks
4. **Provide admin UI** to manage webhook configuration
5. **Enable testing** webhooks before relying on them

## Events That Trigger Notifications

### Problem Reports

- New problem report created (by visitor or staff)
- Problem report closed
- Problem report reopened

### Work Logs

- New log entry created

### Machines & Status/Location Changes

- **Decision:** New machines, status changes, and location changes all automatically generate a log entry. This creates an audit trail without adding friction.

## Event Sources Summary

The notification system watches two event **sources**:

1. **Problem Reports** - new problem reports
2. **Log Entries** - manual work logs + auto-generated for new machines, status changes, location changes, problem reports being closed and re-opened.

## Webhook Configuration

### Multiple Endpoints Per Event

- Each event type can send to zero, one, or many webhook endpoints
- Example: "Problem reports" → Discord Channel A + Slack Channel B + Email webhook
- Endpoints are reusable across event types

### Endpoint Properties

- **Name** (for display in admin UI)
- **URL** (the webhook URL)
- **Enabled/disabled toggle** (per endpoint)
- **Event subscriptions** (which events this endpoint receives)

### Global Controls

- Master enable/disable toggle for all webhooks
- Per-event-type enable/disable toggle
- Per-endpoint enable/disable toggle

## Message Content (v1 - Hard-coded)

### Problem Report Created

- Machine name
- Machine location
- Problem type (e.g., "Won't start", "Stuck ball")
- Description (if provided)
- Reporter name (if provided)
- Link to problem report in web app

### Problem Report Closed/Reopened

- Machine name
- Problem type
- Who changed the status (maintainer name)
- Link to problem report

### Log Entry Created

- Machine name
- Maintainer(s) who did the work (if applicable - auto-generated entries may not have one)
- Work date
- Summary of work performed
- Link to log entry

### Auto-Generated Log Entries (New Machine, Status/Location Change)

- Machine name
- What happened (e.g., "New machine added", "Status: GOOD → BROKEN", "Location: Floor 1 → Floor 2")
- Who made the change (logged-in maintainer)
- Link to log entry

## Testing

### Test Message Capability

- Admin can send a test message to any configured webhook endpoint
- Test message clearly identifies itself as a test
- Test message includes sample data for the event type
- Helps verify webhook URL is correct before relying on it

## Admin UI

### Webhook Endpoints Page

- List all configured webhook endpoints
- Add/edit/delete endpoints
- Enable/disable individual endpoints
- Assign event types to each endpoint
- Send test messages per endpoint

### Global Settings

- Master on/off toggle for all webhooks
- Per-event-type on/off toggle

## Technical Approach

### Async Delivery

- Use Django Q background worker for webhook delivery
- Web requests don't wait for webhook delivery
- Automatic retry on failure with reasonable limits

### Error Handling

- Log failed webhook deliveries
- Don't let webhook failures affect normal app operation

### Security

- Webhook URLs stored securely
- URLs not exposed in logs

## Discord Channel Type Decision

**Decision:** Use regular text channels (not forum channels).

The museum's existing Discord server uses regular text channels. This means:

- No threading support - all notifications are flat posts to the channel
- Simpler implementation - no need to track thread IDs
- Problem reports and their related log entries appear as separate messages in the channel

### Threading (Future Enhancement)

Discord Forum channels support threading via webhooks:

- `thread_name` parameter creates a new thread
- `thread_id` query parameter replies to an existing thread
- Would require storing `discord_thread_id` on ProblemReport model
- Each problem report would become a discussion thread with related work logged underneath

This is deferred since the museum uses regular text channels.

## Future Enhancements (Not in v1)

- Discord Forum channel threading support (problem reports as threads, log entries as replies)
- Field-level customization per event type
- Webhook delivery logs viewable in admin
- Support for different webhook formats (Slack, generic HTTP) beyond Discord
- Rate limiting
- Admin alerts when webhooks consistently fail
