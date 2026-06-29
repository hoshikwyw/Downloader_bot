"""Custom filters for restricting bot access."""
from __future__ import annotations

from aiogram.filters import BaseFilter

from bot.config import settings


class IsAllowed(BaseFilter):
    """Pass only if the sender is in ALLOWED_USER_IDS.

    Works for both messages and callback queries (button clicks) — both expose
    a ``from_user``. If the allow-list is empty, everyone passes (handy on first
    run before you lock the bot down; a warning is logged at startup).
    """

    async def __call__(self, event) -> bool:
        if not settings.allowed_user_ids:
            return True
        user = getattr(event, "from_user", None)
        return user is not None and user.id in settings.allowed_user_ids
