# Discord Local Test

This folder is only for local Discord notification testing.

Required `.env` values:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=target_channel_id
```

The bot must be added to the server and have permission to:

- View Channel
- Send Messages
- Embed Links

Send a sample normalized job embed:

```powershell
.venv\Scripts\python.exe manual\discord_test\send_test_embed.py
```

Preview the payload without sending:

```powershell
.venv\Scripts\python.exe manual\discord_test\send_test_embed.py --dry-run
```
