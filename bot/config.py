"""Loads configuration from environment / .env file."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> set[int]:
    """Parse a comma/space separated list of user IDs into a set of ints."""
    out: set[int] = set()
    for chunk in raw.replace(",", " ").split():
        chunk = chunk.strip()
        if chunk:
            out.add(int(chunk))
    return out


_MB = 1024 * 1024


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_user_ids: set[int]
    local_api_base: str        # e.g. "http://localhost:8081"; empty = Telegram cloud
    max_upload_bytes: int      # 50 MB on cloud, 2 GB on a local Bot API server
    cookies_file: str          # optional yt-dlp cookies.txt (helps when YouTube bot-checks a server IP)
    ytdlp_debug: bool          # YTDLP_DEBUG=1 -> verbose yt-dlp logs (diagnose PO-token / extraction)


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and paste the token "
            "you got from @BotFather."
        )
    allowed = _parse_ids(os.getenv("ALLOWED_USER_IDS", ""))
    local_api = os.getenv("LOCAL_API_BASE", "").strip()
    # A self-hosted Bot API server lifts the send limit from 50 MB to 2 GB.
    max_upload = (2000 if local_api else 50) * _MB

    # Cookies for YouTube. Order: explicit YTDLP_COOKIES path, then Render's
    # secret-file mount, then a cookies.txt in the project root.
    cookies = os.getenv("YTDLP_COOKIES", "").strip()
    if not cookies:
        for candidate in ("/etc/secrets/cookies.txt", "cookies.txt"):
            if os.path.exists(candidate):
                cookies = candidate
                break

    # yt-dlp writes the cookie jar back to this file after each request. Render
    # mounts secret files read-only, so work on a writable copy in the temp dir.
    if cookies and os.path.exists(cookies):
        try:
            writable = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
            if os.path.abspath(cookies) != os.path.abspath(writable):
                shutil.copyfile(cookies, writable)
                cookies = writable
        except OSError:
            pass  # fall back to the original path

    return Settings(
        bot_token=token,
        allowed_user_ids=allowed,
        local_api_base=local_api,
        max_upload_bytes=max_upload,
        cookies_file=cookies,
        ytdlp_debug=bool(os.getenv("YTDLP_DEBUG", "").strip()),
    )


def apply_debug(opts: dict) -> dict:
    """Flip yt-dlp into verbose mode when YTDLP_DEBUG is set (in place)."""
    if settings.ytdlp_debug:
        opts.update(quiet=False, no_warnings=False, verbose=True)
    return opts


settings = load_settings()
