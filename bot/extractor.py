"""yt-dlp wrapper: fetch video metadata (no download) for the format menu."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from yt_dlp import YoutubeDL

from bot.config import apply_debug, settings

# Resolutions we'll offer as buttons, best-first, filtered to what's available.
PREFERRED_HEIGHTS = [2160, 1440, 1080, 720, 480, 360]

# Maps a video id -> its canonical page URL, so button clicks can recover the
# URL without stuffing it into Telegram's 64-byte callback_data. In-memory only
# (fine for a personal bot; cleared on restart).
url_cache: dict[str, str] = {}

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
}

# When YTDLP_DEBUG is on, the last extraction's PO-token-relevant log lines land
# here so the handler can surface them to Telegram (easier than Render logs).
DEBUG_LINES: list[str] = []

_DIAG_KEYWORDS = ("pot", "bgutil", "visitor", "player_client", "innertube", "getpot")


class _DiagLogger:
    """Captures yt-dlp log lines that mention PO-token / client diagnostics."""

    def _keep(self, msg: str, prefix: str = "") -> None:
        low = msg.lower()
        if any(k in low for k in _DIAG_KEYWORDS):
            DEBUG_LINES.append(prefix + msg)

    def debug(self, msg: str) -> None:
        self._keep(msg)

    def info(self, msg: str) -> None:
        self._keep(msg)

    def warning(self, msg: str) -> None:
        self._keep(msg, "WARN: ")

    def error(self, msg: str) -> None:  # keep all errors short
        DEBUG_LINES.append("ERR: " + msg)


@dataclass
class VideoInfo:
    id: str
    title: str
    url: str
    uploader: str
    duration: int            # seconds, 0 if unknown
    thumbnail: str | None
    heights: list[int]       # available video heights, sorted high -> low
    source: str              # extractor name, e.g. "Youtube"


def _extract(url: str) -> VideoInfo:
    opts = dict(_YDL_OPTS)
    if settings.cookies_file:
        opts["cookiefile"] = settings.cookies_file
    apply_debug(opts)
    if settings.ytdlp_debug:
        DEBUG_LINES.clear()
        opts["logger"] = _DiagLogger()
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # If a playlist slipped through, use the first entry.
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    formats = info.get("formats") or []
    heights = sorted(
        {
            f["height"]
            for f in formats
            if f.get("vcodec") not in (None, "none") and f.get("height")
        },
        reverse=True,
    )

    return VideoInfo(
        id=info.get("id", ""),
        title=(info.get("title") or "(untitled)")[:200],
        url=info.get("webpage_url") or url,
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=int(info.get("duration") or 0),
        thumbnail=info.get("thumbnail"),
        heights=heights,
        source=info.get("extractor_key") or info.get("extractor") or "",
    )


async def fetch_info(url: str) -> VideoInfo:
    """Extract metadata off the event loop (yt-dlp is blocking)."""
    return await asyncio.to_thread(_extract, url)


def menu_heights(info: VideoInfo, limit: int = 4) -> list[int]:
    """Pick up to `limit` resolutions to show as buttons."""
    avail = set(info.heights)
    chosen = [h for h in PREFERRED_HEIGHTS if h in avail]
    if not chosen:  # extractor didn't report standard heights — fall back
        chosen = info.heights
    return chosen[:limit]
