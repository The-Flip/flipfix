# Discord Integration

Flipfix integrates with Discord in two directions:

- **[Flipfix → Discord](#flipfix-to-discord)**: Flipfix can post notifications to Discord when records are created
- **[Discord → Flipfix](#discord-to-flipfix)**: Users can right-click Discord messages to create records in Flipfix via an AI-assisted flow

Both are optional and configured independently via Django Admin → Constance → Config.

<a id="flipfix-to-discord"></a>

## Flipfix → Discord (Webhooks)

Configure the system to post to Discord when problem reports, log entries, or parts requests are created.

### Setup

#### 1. Create a webhook in Discord

- In Discord, go to Server Settings → Integrations → Webhooks
- Click "New Webhook"
- Choose the channel for notifications
- Copy the webhook URL

#### 2. Configure in Django Admin

- Go to Admin → Constance → Config
- Set `DISCORD_WEBHOOK_URL` to the webhook URL
- Set `DISCORD_WEBHOOKS_ENABLED` = True

### Coalescing (debounced notifications)

A single stretch of work by one person can create many records in a few minutes
(adding a machine auto-creates a log entry, a status change another, plus any
problem reports), which floods the channel. Coalescing waits for the person to
finish, then posts **one message per machine they worked on**.

- Set `DISCORD_NOTIFICATION_COALESCING_ENABLED` = True (Admin → Constance → Config).
- **How it works:** each would-fire event is buffered in the `PendingNotification`
  table. The `flush-discord-notifications` schedule runs every minute and delivers
  a person's buffer once they've been quiet for **5 minutes**, or after a
  **15-minute** cap for someone working continuously.
- **What gets posted.** The buffer is grouped by machine, since that is what makes
  a set of records one piece of work. Each group goes one of two ways:
  - **Somebody wrote something** — a repair note, problem report or parts request.
    That becomes a full post with its body text and its photos, and the rest of
    the group (status change, move to the floor, reports closed) is listed
    underneath it. Fixing two machines therefore posts twice.
  - **Nothing but recorded actions** — status flips, location moves. Every such
    group for that person merges into one summary grouped by action, e.g.
    "Moved to the floor: Comet, Cyclone, Star Trek".
- **The grouping key is who _saved_ the record**, taken from the
  `django-simple-history` creation row, not the record's attribution field
  (`reported_by_user`/`requested_by`/`posted_by`). Attribution is null whenever
  someone files on another person's behalf, which would otherwise make most
  records look anonymous. `WebhookHandler.get_submitting_user()` falls back to
  attribution for records created outside a request (the bot, management commands).
- **Signed-out events are never debounced.** Visitor problem reports from the
  public QR flow post immediately, so the floor still gets real-time alerts.
- **Requires the background worker.** Buffered events are only delivered by the
  qcluster worker (`make runq`) running the flush schedule; ensure it's up and that
  `ensure_scheduled_tasks` has run (it runs at deploy). With coalescing off, every
  event posts immediately as before.
- **At most four full posts per flush.** Grouping per machine means a session
  touching twenty machines would otherwise post twenty times. Past
  `MAX_RICH_POSTS_PER_FLUSH`, the remaining machines give up their own post and
  become lines in the summary message. The ones that keep a full post are those
  with the most hand-written text, so the cap never sacrifices a long repair
  write-up to make room for a one-word note. A summary line carries no body text,
  so a demoted record does lose its wording — that is the trade for bounded volume.
- Tuning: the 5-/15-minute windows are `COALESCE_QUIET_PERIOD` / `COALESCE_MAX_WAIT`
  in `flipfix/apps/discord/tasks.py`, alongside `MAX_RICH_POSTS_PER_FLUSH`; the body
  cap is `NOTIFICATION_BODY_MAX_WORDS` in `formatters.py`.

Two dev-only management commands work on the historical stream, both reading local
history only — neither writes data or contacts Discord:

- `analyze_notification_clusters` reconstructs the stream and clusters it, for
  re-evaluating the debounce windows.
- `replay_notification_coalescing` replays it through the live coalescer and writes
  `discord_coalescing_cases.md`, an evidence document showing what the channel would
  actually receive. That output is **deliberately not committed**: it reproduces real
  maintainer usernames and the text of real reports, and this repository is public.
  Generate it locally when you need it, and re-run after changing the formatters or
  the grouping rules to see what moved:

  ```bash
  make db-up && scripts/sync_prod.sh --yes    # sanitized production data
  DJANGO_SETTINGS_MODULE=flipfix.settings.dev .venv/bin/python manage.py \
      replay_notification_coalescing
  ```

  It picks its cases by rule (biggest session, most photos, longest write-up, …)
  rather than by hard-coded ids, so the document survives a re-sync.

### Keeping routine paperwork out of the channel

Problem reports and log entries have an `announce` flag, surfaced as an
"Announce this in Discord" checkbox on the create forms. Unticking it records the
entry normally but posts nothing — intended for paperwork such as a pasted intake
checklist.

A wiki template can preset it. Add `announce="no"` to the template's
`template:action` marker and the create form unticks the box whenever that
template is chosen:

```html
<!-- template:action name="intake" action="button,option" type="problem"
     label="Intake checklist" announce="no" -->
```

Records without the field (parts requests and their updates) always announce.

<a id="discord-to-flipfix"></a>

## Discord → Flipfix (Discord Bot)

Adds a "Add to Flipfix" right-click context menu command in Discord. Users right-click a message, the bot sends information about that message and previous messages to a LLM (Claude, currently) for analysis, and presents suggested records to create.

### How the Bot Works

1. User right-clicks a message in Discord → "Add to Flipfix"
2. Bot gathers the target message plus surrounding context (up to 30 prior messages)
3. Bot sends that context to the LLM (Claude) for analysis
4. The LLM suggests records to create (log entries, problem reports, or part requests)
5. User reviews suggestions one at a time, can skip or edit each
6. Bot creates the user-confirmed records in Flipfix. The bot links Discord users to Flipfix maintainers by matching usernames.
7. Bot saves the ID of the Discord message to Flipfix to prevent duplicate processing

This will incur LLM costs based on usage _(~$0.01-0.05 per analysis)_.

This puts the _Add to Flipfix_ right-click menu item on every message in every channel on the Discord server. We can restrict it to just the Workshop channel if we decide we like this feature enough to keep it.

### Setting up the Bot

Involves a few separate areas:

- [A. Get an Anthropic API Key](#llm-api-key)
- [B. Setup in Discord Developer Portal](#discord-developer-portal)
- [C. Configure in Django Admin](#django-admin-bot-config)

<a id="llm-api-key"></a>

### A. Get an Anthropic API Key

1. Go to https://console.anthropic.com/
2. Create an API key

<a id="discord-developer-portal"></a>

### B. Setup in Discord Developer Portal

1. **Create a Discord application:**
   - Go to https://discord.com/developers/applications
   - Click "New Application", name it (e.g., "Flipfix Bot")

2. **Create the bot:**
   - Go to the "Bot" tab
   - Click "Add Bot"
   - Copy the **Token** (you'll need this later)
   - Under "Privileged Gateway Intents", enable:
     - Message Content Intent
     - Server Members Intent (optional, for user linking)

3. **Generate an invite URL:**
   - Go to "OAuth2" → "URL Generator"
   - Select scopes: `bot`, `applications.commands`
   - Select bot permissions: `Send Messages`, `Read Message History`
   - Copy the generated URL and open it to invite the bot to your server

4. **Get your Guild ID:**
   - In Discord, enable Developer Mode _(User Settings → Advanced → Developer Mode)_
   - Right-click your server name → "Copy Server ID"
   - This is your Guild ID

<a id="django-admin-bot-config"></a>

### C. Configure Bot in Django Admin

Go to Admin → Constance → Config and set:

| Setting               | Value                                        |
| --------------------- | -------------------------------------------- |
| `DISCORD_BOT_ENABLED` | True                                         |
| `DISCORD_BOT_TOKEN`   | Your bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID`    | Your Discord server ID                       |
| `ANTHROPIC_API_KEY`   | Your Anthropic API key                       |
