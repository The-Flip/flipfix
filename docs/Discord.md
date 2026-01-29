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
- Optionally disable specific event types:
  - `DISCORD_WEBHOOKS_PROBLEM_REPORTS`
  - `DISCORD_WEBHOOKS_LOG_ENTRIES`
  - `DISCORD_WEBHOOKS_PARTS`

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
