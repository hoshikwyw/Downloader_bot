"""Entry point: starts the bot with long polling (outbound only — no public IP needed)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from bot.config import settings
from bot.handlers import basic, download
from bot.health import start_health_server

logger = logging.getLogger("downloader-bot")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not settings.allowed_user_ids:
        logger.warning(
            "ALLOWED_USER_IDS is empty — the bot will respond to EVERYONE. "
            "Send /id to the bot, then set ALLOWED_USER_IDS in .env and restart."
        )

    session = None
    if settings.local_api_base:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(settings.local_api_base, is_local=True)
        )
        logger.info(
            "Using local Bot API server at %s (uploads up to 2 GB).",
            settings.local_api_base,
        )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()
    dp.include_router(basic.public_router)
    dp.include_router(download.router)      # link + format buttons
    dp.include_router(basic.private_router)  # echo fallback (must be last)

    me = await bot.get_me()
    logger.info("Starting @%s (id=%s) ...", me.username, me.id)

    # Keep-alive endpoint for hosted web services (no-op locally).
    await start_health_server()

    # Drop any updates that piled up while the bot was offline.
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
