#!/usr/bin/env sh
set -e

# Start the YouTube PO-token provider on 127.0.0.1:4416 in the background.
# yt-dlp's bgutil plugin auto-detects it at this default address.
echo "Starting PO-token provider on 127.0.0.1:4416 ..."
node /opt/bgutil/build/main.js &

# Start the bot in the foreground.
exec python -m bot.main
