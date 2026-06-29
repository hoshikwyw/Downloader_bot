"""Actual media downloading (yt-dlp + ffmpeg). M2: audio -> MP3."""
from __future__ import annotations

import asyncio
import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL

from bot.config import apply_debug, settings

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


def _resolve_ffmpeg_dir() -> str | None:
    """Find ffmpeg's bin dir even if it isn't on PATH (common winget quirk).

    Order: FFMPEG_LOCATION env override -> PATH -> winget default install path.
    """
    override = os.getenv("FFMPEG_LOCATION", "").strip()
    if override and Path(override).exists():
        return override

    on_path = shutil.which("ffmpeg")
    if on_path:
        return str(Path(on_path).parent)

    local = os.getenv("LOCALAPPDATA")
    if local:
        pattern = os.path.join(
            local, "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe",
        )
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return str(Path(matches[0]).parent)
    return None


# Resolved once at import. yt-dlp is pointed here so downloads work regardless
# of whether the user's shell PATH has been refreshed after installing ffmpeg.
FFMPEG_DIR = _resolve_ffmpeg_dir()

# Max size a bot can send: 50 MB on Telegram's cloud API, 2 GB when a local Bot
# API server is configured (LOCAL_API_BASE). Driven by config.
TELEGRAM_BOT_FILE_LIMIT = settings.max_upload_bytes


@dataclass
class AudioResult:
    path: Path
    title: str
    performer: str
    duration: int
    filesize: int


@dataclass
class VideoResult:
    path: Path | None        # None when too_large (nothing to send)
    title: str
    duration: int
    width: int
    height: int
    filesize: int            # actual size, or pre-download estimate if too_large
    too_large: bool


def ffmpeg_available() -> bool:
    return FFMPEG_DIR is not None


def _download_audio(url: str, bitrate: str = "192") -> AudioResult:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            }
        ],
    }
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    if settings.cookies_file:
        opts["cookiefile"] = settings.cookies_file
    apply_debug(opts)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    # Prefer the exact post-processed path yt-dlp reports; fall back to id.mp3.
    path: Path | None = None
    for d in info.get("requested_downloads") or []:
        if d.get("filepath"):
            path = Path(d["filepath"])
            break
    if path is None:
        path = DOWNLOAD_DIR / f"{info.get('id', 'audio')}.mp3"

    return AudioResult(
        path=path,
        title=(info.get("title") or info.get("id") or "audio")[:100],
        performer=(info.get("uploader") or info.get("channel") or "")[:100],
        duration=int(info.get("duration") or 0),
        filesize=path.stat().st_size if path.exists() else 0,
    )


async def download_audio(url: str, bitrate: str = "192") -> AudioResult:
    """Download bestaudio and convert to MP3 off the event loop."""
    return await asyncio.to_thread(_download_audio, url, bitrate)


def _fmt_size(f: dict) -> int:
    return f.get("filesize") or f.get("filesize_approx") or 0


def _is_watermarked(f: dict) -> bool:
    """TikTok's watermarked stream shows up as a 'download'/'watermark' format."""
    tag = (str(f.get("format_id", "")) + " " + str(f.get("format_note", ""))).lower()
    return "watermark" in tag or "download" in tag


def _pick_tiktok_format(info: dict) -> str | None:
    """Choose the best NON-watermarked TikTok video format id (lossless clean source)."""
    videos = [f for f in (info.get("formats") or []) if f.get("vcodec") not in (None, "none")]
    if not videos:
        return None
    clean = [f for f in videos if not _is_watermarked(f)]
    pool = clean or videos  # if somehow all flagged, fall back rather than fail
    best = max(pool, key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0)))
    return best.get("format_id")


def _estimate_size(info: dict, height: int) -> int | None:
    """Best-effort merged size = best video (<=height) + best audio.

    Returns None when sizes aren't reported (then we fall back to a
    post-download size check).
    """
    formats = info.get("formats") or []
    video_only = [
        f for f in formats
        if f.get("vcodec") not in (None, "none")
        and f.get("acodec") in (None, "none")
        and (f.get("height") or 0) <= height
    ]
    audio_only = [
        f for f in formats
        if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
    ]
    if video_only:
        best_v = max(video_only, key=lambda f: (f.get("height") or 0, _fmt_size(f)))
        best_a = max((_fmt_size(a) for a in audio_only), default=0)
        total = _fmt_size(best_v) + best_a
        return total or None

    # No separate streams — look for a progressive (combined) format.
    progressive = [
        f for f in formats
        if f.get("vcodec") not in (None, "none")
        and f.get("acodec") not in (None, "none")
        and (f.get("height") or 0) <= height
    ]
    if progressive:
        best = max(progressive, key=lambda f: (f.get("height") or 0, _fmt_size(f)))
        return _fmt_size(best) or None
    return None


def _download_video(url: str, height: int) -> VideoResult:
    base: dict = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if FFMPEG_DIR:
        base["ffmpeg_location"] = FFMPEG_DIR
    if settings.cookies_file:
        base["cookiefile"] = settings.cookies_file
    apply_debug(base)

    # 1. Probe metadata + estimate size before spending bandwidth.
    with YoutubeDL(base) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    title = (info.get("title") or info.get("id") or "video")[:100]
    duration = int(info.get("duration") or 0)
    is_tiktok = "tiktok" in (info.get("extractor_key") or "").lower()

    estimate = _estimate_size(info, height)
    if estimate and estimate > TELEGRAM_BOT_FILE_LIMIT:
        return VideoResult(None, title, duration, 0, 0, estimate, too_large=True)

    # 2. Pick the format. TikTok = best no-watermark stream (already combined,
    # no merge). Otherwise = best video up to `height` + best audio, merged.
    opts = dict(base)
    opts["outtmpl"] = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    if is_tiktok:
        tiktok_fmt = _pick_tiktok_format(info)
        opts["format"] = tiktok_fmt or "best"
    else:
        opts["format"] = (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        )
        opts["merge_output_format"] = "mp4"
    with YoutubeDL(opts) as ydl:
        dinfo = ydl.extract_info(url, download=True)
    if dinfo.get("_type") == "playlist" and dinfo.get("entries"):
        dinfo = dinfo["entries"][0]

    path: Path | None = None
    for d in dinfo.get("requested_downloads") or []:
        if d.get("filepath"):
            path = Path(d["filepath"])
            break
    if path is None:
        path = DOWNLOAD_DIR / f"{dinfo.get('id', 'video')}.mp4"

    size = path.stat().st_size if path.exists() else 0
    width = int(dinfo.get("width") or 0)
    real_height = int(dinfo.get("height") or height)

    # 3. Post-download guard (estimate may have been missing/low).
    if size > TELEGRAM_BOT_FILE_LIMIT:
        cleanup(path)
        return VideoResult(None, title, duration, width, real_height, size, too_large=True)

    return VideoResult(path, title, duration, width, real_height, size, too_large=False)


async def download_video(url: str, height: int) -> VideoResult:
    """Download a video up to `height`p, merged to MP4, off the event loop."""
    return await asyncio.to_thread(_download_video, url, height)


def cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
