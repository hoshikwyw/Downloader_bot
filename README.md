# Downloader Bot

A personal **Telegram bot** to download videos & music from YouTube (and later TikTok,
no-watermark). Runs on your own laptop — free, no cloud, no credit card. Works from your
phone and your laptop because the interface *is* Telegram.

> Status: **M0 — bot skeleton** (token + private access lock + echo). Downloading lands in M1+.

## How it works

The bot runs on your laptop and connects **outbound** to Telegram (long polling), so you
don't need a public IP, port forwarding, or any tunnel. You paste a link in the chat; the
bot downloads it on your machine and sends the file back to you.

## Setup (Windows / PowerShell)

### 1. Create your bot & get a token
1. Open Telegram → search **@BotFather**.
2. Send `/newbot`, pick a name and a username ending in `bot`.
3. Copy the **token** it gives you (looks like `123456:ABC-DEF...`).

### 2. Configure
```powershell
copy .env.example .env
```
Open `.env` and paste your token into `BOT_TOKEN=`. Leave `ALLOWED_USER_IDS` empty for now.

### 3. Install dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Run
```powershell
python -m bot.main
```
You should see `Starting @your_bot ...`. In Telegram, open your bot and send `/start`.

### 5. Lock it to just you
Send the bot `/id`. It replies with your numeric user ID. Paste that into
`ALLOWED_USER_IDS=` in `.env`, then stop the bot (Ctrl+C) and run it again. Now only you
can use it.

## Progress

- **M0** ✅ bot skeleton + private access lock
- **M1** ✅ paste a link → title, thumbnail & format buttons (MP4 / MP3)
- **M2** ✅ deliver MP3 (audio)
- **M3** ✅ deliver MP4 (merge video+audio, pre-download size guard)
- **M4** ✅ optional self-hosted Bot API server → 2 GB uploads (code done; see below)
- **M5** ⏭️ TikTok no-watermark

> **ffmpeg** is required from M2 onward. Install with `winget install Gyan.FFmpeg`. The bot
> auto-finds it even if it isn't on your PATH yet.

## Optional: 2 GB uploads (M4)

By default the bot uses Telegram's cloud API, which caps bot file sends at **50 MB**. To send
files up to **2 GB**, run your own Bot API server (needs Docker):

1. Get `api_id` / `api_hash` from <https://my.telegram.org> → *API development tools*.
2. Put `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`.
3. Start the server:
   ```bash
   docker compose up -d
   ```
4. Set `LOCAL_API_BASE=http://localhost:8081` in `.env`, then restart the bot.

If sending fails with a migration error the first time, log the bot out of the cloud API once:
`curl "https://api.telegram.org/bot<YOUR_TOKEN>/logOut"`, then start the server and bot again.

## Deploy to Render (always-on, free)

Hosts the bot 24/7 so your laptop doesn't have to run. Render free needs no credit card.

1. Push this repo to GitHub.
2. In Render: **New + → Blueprint**, select the repo (uses `render.yaml`), or **New + →
   Web Service → Docker** and point it at the repo.
3. Set environment variables in the Render dashboard:
   - `BOT_TOKEN` — your BotFather token
   - `ALLOWED_USER_IDS` — your Telegram user ID
4. Deploy. Watch the logs for `Starting @your_bot …`.
5. **Keep it awake:** free web services sleep after ~15 min idle. Add a free uptime pinger
   (e.g. <https://cron-job.org> or UptimeRobot) hitting `https://<your-app>.onrender.com/health`
   every ~10 minutes.

**Gotchas**
- Only run **one** copy of the bot at a time (Telegram allows a single poller per token) —
  stop the laptop instance before/while Render runs it.
- Render uses datacenter IPs; YouTube may show *"confirm you're not a bot."* If so, export
  your browser cookies to a `cookies.txt` and set `YTDLP_COOKIES` (or commit the file —
  but it's git-ignored by default for safety). TikTok is unaffected.

