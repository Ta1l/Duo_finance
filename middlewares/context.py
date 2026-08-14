"""Middleware: сессия БД на событие + жёсткий контроль доступа к приватному боту."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Config
from database import crud


class ContextMiddleware(BaseMiddleware):
    """
    Для каждого апдейта:
    - открывает AsyncSession и кладёт в data["session"];
    - подгружает пользователя в data["db_user"] (None, если не зарегистрирован);
    - отсекает незарегистрированных (боt приватный, ровно 2 слота), кроме /start;
    - при исключении откатывает транзакцию.
    """

    def __init__(self, session_pool: async_sessionmaker[AsyncSession], config: Config) -> None:
        self._session_pool = session_pool
        self._config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None:
            return await handler(event, data)

        is_start_cmd = False
        if isinstance(event, Message):
            tokens = (event.text or "").strip().split(maxsplit=1)
            first_token = tokens[0].lower() if tokens else ""
            command = first_token.split("@", maxsplit=1)[0]
            is_start_cmd = command == "/start"

        async with self._session_pool() as session:
            db_user = await crud.get_by_tg(session, tg_user.id)

            if db_user is None and not is_start_cmd:
                if isinstance(event, Message):
                    await event.answer(
                        "🚫 Это приватный бот для двух игроков. "
                        "Если ты один из них — нажми /start."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("Нет доступа.", show_alert=True)
                return None

            data["session"] = session
            data["db_user"] = db_user
            data["config"] = self._config
            try:
                return await handler(event, data)
            except Exception:
                await session.rollback()
                raise
