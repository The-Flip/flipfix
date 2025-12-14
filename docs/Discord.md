# Discord Integration

Flipfix integrates with Discord in two directions:

- **Outbound (Webhooks)**: Flipfix posts notifications to Discord when records are created
- **Inbound (Bot)**: Users right-click Discord messages to create Flipfix records via an LLM-assisted flow

Both are optional and configured independently via Django Admin → Constance → Config.

## Outbound: Webhooks

Posts to Discord when problem reports, log entries, or part requests are created.

### Setup

1. **Create a Discord webhook:**
   - In Discord, go to Server Settings → Integrations → Webhooks
   - Click "New Webhook"
   - Choose the channel for notifications
   - Copy the webhook URL

2. **Configure in Django Admin:**
   - Go to Admin → Constance → Config
   - Set `DISCORD_WEBHOOK_URL` to the webhook URL
   - Set `DISCORD_WEBHOOKS_ENABLED` = True
   - Optionally disable specific event types:
     - `DISCORD_WEBHOOKS_PROBLEM_REPORTS`
     - `DISCORD_WEBHOOKS_LOG_ENTRIES`
     - `DISCORD_WEBHOOKS_PARTS`

Webhooks are delivered asynchronously by the worker service.

## Inbound: Bot

Adds a "Add to Flipfix" context menu command in Discord. Users right-click a message, the bot gathers context, sends it to Claude for analysis, and presents suggested records to create.

### Discord Developer Portal Setup

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
   - In Discord, enable Developer Mode (User Settings → Advanced → Developer Mode)
   - Right-click your server name → "Copy Server ID"
   - This is your Guild ID

### Anthropic API Setup

1. Go to https://console.anthropic.com/
2. Create an API key
3. Note: This will incur costs based on usage (~$0.01-0.05 per analysis)

### Django Admin Configuration

Go to Admin → Constance → Config and set:

| Setting | Value |
|---------|-------|
| `DISCORD_BOT_ENABLED` | True |
| `DISCORD_BOT_TOKEN` | Your bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID` | Your server ID |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

### Railway Service Setup

The bot runs as a separate Railway service:

1. In Railway, create a new service in your project
2. Connect to the same GitHub repo
3. Set **Config Path** to `railpack.bot.json`
4. Ensure it has access to the shared `DATABASE_URL`
5. No public domain needed (the bot connects outbound to Discord)

Resource recommendations: 0.5 vCPU, 512 MB memory.

## How the Bot Works

1. User right-clicks a message in Discord → "Add to Flipfix"
2. Bot gathers the target message plus surrounding context (up to 30 prior messages)
3. Context is sent to Claude for analysis
4. Claude suggests records to create (log entries, problem reports, or part requests)
5. User reviews suggestions one at a time, can edit or skip each
6. Confirmed records are created in Flipfix
7. Bot links the Discord message to prevent duplicate processing

The bot automatically links Discord users to Flipfix maintainers by matching usernames.
