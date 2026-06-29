"""M1 handlers: detect a link, show metadata + format buttons.

The buttons are wired up but don't download yet — that arrives in M2 (MP3) and
M3 (MP4). Clicking one shows a placeholder for now.
"""
from __future__ import annotations

import html
import re

from aiogram import Router
from aiogram.filters import BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.downloader import (
    TELEGRAM_BOT_FILE_LIMIT,
    cleanup,
    download_audio,
    download_video,
    ffmpeg_available,
)
from bot.extractor import VideoInfo, fetch_info, menu_heights, url_cache
from bot.filters import IsAllowed

URL_RE = re.compile(r"https?://\S+")

router = Router(name="download")
router.message.filter(IsAllowed())
router.callback_query.filter(IsAllowed())


class ContainsURL(BaseFilter):
    """Match messages containing a URL; inject the URL as `url` into the handler."""

    async def __call__(self, message: Message):
        if not message.text:
            return False
        m = URL_RE.search(message.text)
        return {"url": m.group(0)} if m else False


class DLChoice(CallbackData, prefix="dl"):
    kind: str    # "v" = video, "a" = audio
    height: int  # 0 for audio
    vid: str     # video id (key into url_cache)


def fmt_duration(sec: int) -> str:
    if not sec:
        return "?"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_caption(info: VideoInfo) -> str:
    line_uploader = f"👤 {html.escape(info.uploader)}\n" if info.uploader else ""
    return (
        f"<b>{html.escape(info.title)}</b>\n"
        f"{line_uploader}"
        f"⏱ {fmt_duration(info.duration)}   📺 {html.escape(info.source)}\n\n"
        "Choose a format:"
    )


def build_keyboard(info: VideoInfo):
    kb = InlineKeyboardBuilder()
    if "tiktok" in info.source.lower():
        # TikTok: single clean (no-watermark) video button; resolution choice
        # isn't meaningful for a portrait clip.
        kb.button(
            text="🎬 Video (no watermark)",
            callback_data=DLChoice(kind="v", height=0, vid=info.id),
        )
    else:
        for h in menu_heights(info):
            kb.button(
                text=f"🎬 {h}p",
                callback_data=DLChoice(kind="v", height=h, vid=info.id),
            )
    kb.button(
        text="🎵 MP3",
        callback_data=DLChoice(kind="a", height=0, vid=info.id),
    )
    kb.adjust(2)
    return kb.as_markup()


@router.message(ContainsURL())
async def on_link(message: Message, url: str) -> None:
    status = await message.answer("🔎 Fetching link info…")
    try:
        info = await fetch_info(url)
    except Exception as e:  # yt-dlp raises various extractor errors
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg:
            await status.edit_text(
                "⚠️ <b>YouTube isn't available on this hosted bot</b> — YouTube "
                "blocks the server's IP address.\n\n"
                "✅ <b>TikTok works fine here</b> — send a TikTok link.\n\n"
                "<i>(YouTube only works when the bot runs on a home/residential "
                "connection, not a datacenter.)</i>"
            )
        else:
            await status.edit_text(
                "❌ Couldn't read that link.\n"
                f"<code>{html.escape(msg)[:300]}</code>"
            )
        return

    url_cache[info.id] = info.url
    caption = build_caption(info)
    keyboard = build_keyboard(info)

    try:
        if info.thumbnail:
            await message.answer_photo(info.thumbnail, caption=caption, reply_markup=keyboard)
        else:
            await message.answer(caption, reply_markup=keyboard)
    except Exception:
        # Telegram couldn't fetch the thumbnail — fall back to plain text.
        await message.answer(caption, reply_markup=keyboard)
    finally:
        await status.delete()


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return (name or "audio")[:80]


@router.callback_query(DLChoice.filter())
async def on_choice(query: CallbackQuery, callback_data: DLChoice) -> None:
    url = url_cache.get(callback_data.vid)
    if not url:
        await query.answer("This menu expired — please send the link again.", show_alert=True)
        return

    if callback_data.kind == "a":
        await _handle_audio(query, url)
    else:
        await _handle_video(query, url, callback_data.height)


async def _handle_audio(query: CallbackQuery, url: str) -> None:
    if not ffmpeg_available():
        await query.answer()
        await query.message.answer(
            "⚙️ <b>ffmpeg isn't installed yet</b> — it's needed to make MP3s.\n"
            "Install it, then restart the bot:\n"
            "<code>winget install Gyan.FFmpeg</code>"
        )
        return

    await query.answer("Downloading…")
    status = await query.message.answer("🎵 Downloading audio… this can take a moment.")
    try:
        result = await download_audio(url)
    except Exception as e:
        await status.edit_text(
            "❌ Download failed.\n"
            f"<code>{html.escape(str(e))[:300]}</code>"
        )
        return

    if result.filesize == 0:
        await status.edit_text("❌ Something went wrong — no audio file was produced.")
        return

    if result.filesize > TELEGRAM_BOT_FILE_LIMIT:
        cleanup(result.path)
        mb = result.filesize / 1024 / 1024
        await status.edit_text(
            f"⚠️ The MP3 is {mb:.1f} MB, over Telegram's 50 MB bot limit.\n"
            "We'll lift this in M4 (self-hosted Bot API server → 2 GB)."
        )
        return

    await status.edit_text("⬆️ Uploading to Telegram…")
    audio = FSInputFile(result.path, filename=f"{_safe_filename(result.title)}.mp3")
    try:
        await query.message.answer_audio(
            audio,
            title=result.title,
            performer=result.performer or None,
            duration=result.duration or None,
        )
        await status.delete()
    finally:
        cleanup(result.path)


async def _handle_video(query: CallbackQuery, url: str, height: int) -> None:
    if not ffmpeg_available():
        await query.answer()
        await query.message.answer(
            "⚙️ <b>ffmpeg isn't installed yet</b> — it's needed to merge video + audio.\n"
            "Install it, then restart the bot:\n"
            "<code>winget install Gyan.FFmpeg</code>"
        )
        return

    label = f"{height}p" if height else "video"
    await query.answer("Downloading…")
    status = await query.message.answer(
        f"🎬 Downloading {label}… this can take a while."
    )
    try:
        result = await download_video(url, height)
    except Exception as e:
        await status.edit_text(
            "❌ Download failed.\n"
            f"<code>{html.escape(str(e))[:300]}</code>"
        )
        return

    if result.too_large:
        mb = result.filesize / 1024 / 1024
        await status.edit_text(
            f"⚠️ {label} is ~{mb:.0f} MB, over Telegram's 50 MB bot limit.\n"
            "Try a lower resolution or 🎵 MP3, or enable the 2 GB server (M4)."
        )
        return

    if not result.path or result.filesize == 0:
        await status.edit_text("❌ Something went wrong — no video file was produced.")
        return

    await status.edit_text("⬆️ Uploading to Telegram…")
    video = FSInputFile(result.path, filename=f"{_safe_filename(result.title)}.mp4")
    try:
        await query.message.answer_video(
            video,
            caption=result.title,
            width=result.width or None,
            height=result.height or None,
            duration=result.duration or None,
            supports_streaming=True,
        )
        await status.delete()
    finally:
        cleanup(result.path)
