# Hosting the Discord Bot

## Recommended Option: Railway

Railway is a good fit for this bot because it can run a long-lived worker process. The bot does not need an inbound public web server; it just needs to stay connected to Discord.

1. Push this project to GitHub.
2. Create a Railway project from the GitHub repo.
3. Railway should detect `railway.toml` and run:

```bash
python main.py
```

4. Add these environment variables in Railway:

```env
DISCORD_TOKEN=your_real_bot_token
GUILD_ID=your_discord_server_id
MOD_LOG_CHANNEL=0
```

5. Deploy the project.
6. Check the deploy logs for a line like:

```text
Synced slash commands to guild ...
```

## Important Discord Invite Scope

If slash commands do not show up, reinvite the bot with both scopes:

```text
bot
applications.commands
```

The bot also needs the server permissions for the features you use:

- Send Messages
- Read Message History
- Manage Messages
- Moderate Members
- Ban Members
- Kick Members
- Manage Roles

For moderation to work, the bot's highest role must be above the roles it needs to moderate.

## Fly.io

This repo includes a `Dockerfile` and `fly.toml` for Fly.io.

If your Fly app name is not `norm-bot`, update this line in `fly.toml`:

```toml
app = "norm-bot"
```

Set secrets before deploying:

```bash
fly secrets set DISCORD_TOKEN=your_real_bot_token GUILD_ID=your_discord_server_id MOD_LOG_CHANNEL=0
```

Then deploy:

```bash
fly deploy
```

If Fly says the app is not listening on a port, that is okay for this bot as long as it is only a warning. This bot is a worker process and does not need an HTTP service.

If the Machine starts and then exits, check logs:

```bash
fly logs
```

Common causes:

- `DISCORD_TOKEN` is missing or wrong.
- The bot token was reset in the Discord Developer Portal.
- The app name in `fly.toml` does not match your Fly app.
- The bot was invited without the `applications.commands` scope.

## Other Hosting Options

Render can work, but use a paid Background Worker. Free Render web services spin down when idle, which is not good for a Discord bot.

A cheap VPS also works. Install Python, install `requirements.txt`, set environment variables, and keep the bot running with `systemd`, `pm2`, or Docker.
