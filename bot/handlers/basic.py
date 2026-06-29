"""M0 handlers: /start, /id, and a simple echo to prove the bot is alive.

Real download handlers arrive in M1+. The /id command is intentionally open to
everyone so you can discover your own user ID and put it in ALLOWED_USER_IDS.
Everything else is gated behind the IsAllowed filter.
"""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.filters import IsAllowed

# Open to everyone — lets a new user look up their ID to lock the bot down.
public_router = Router(name="public")

# Gated — only ALLOWED_USER_IDS reach these handlers.
private_router = Router(name="private")
private_router.message.filter(IsAllowed())


@public_router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    user = message.from_user
    uid = user.id if user else "unknown"
    await message.answer(
        f"Your Telegram user ID is <code>{uid}</code>.\n\n"
        "Put this in <code>ALLOWED_USER_IDS</code> in your <code>.env</code> "
        "file, then restart the bot to make it private to you."
    )


@public_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Downloader bot</b> is online.\n\n"
        "This is the M0 skeleton — paste-a-link downloading comes next.\n\n"
        "Commands:\n"
        "• /id — show your Telegram user ID\n"
        "• send any text — I'll echo it back (proof I'm alive)"
    )


@private_router.message(F.text)
async def echo(message: Message) -> None:
    await message.answer(f"You said: {html.escape(message.text or '')}")
