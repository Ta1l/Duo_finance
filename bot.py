"""Точка входа: python bot.py"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database.engine import init_models, make_engine, make_session_factory
from handlers import daily, start
from middlewares.context import ContextMiddleware
from scheduler.jobs import setup_scheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("duo_finance_bot")

    config = load_config()
    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else None

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    engine = make_engine(config.database_url)
    session_pool = make_session_factory(engine)
    await init_models(engine)

    storage = MemoryStorage()  # для прода: RedisStorage
    dp = Dispatcher(storage=storage)

    context_mw = ContextMiddleware(session_pool=session_pool, config=config)
    dp.message.outer_middleware(context_mw)
    dp.callback_query.outer_middleware(context_mw)

    # Порядок важен: команды start.py (start/status/help, fallthrough без state),
    # затем FSM-шаги daily.py (/cancel, /report, шаги опроса).
    dp.include_router(start.router)
    dp.include_router(daily.router)

    dp["config"] = config
    dp["session_pool"] = session_pool

    me = await bot.get_me()
    log.info("Авторизован как @%s (id=%s)", me.username, me.id)

    scheduler = setup_scheduler(
        bot=bot,
        bot_id=me.id,
        dp_storage=storage,
        session_pool=session_pool,
        config=config,
    )
    scheduler.start()
    log.info(
        "Планировщик запущен: опрос %02d:%02d МСК ежедневно, выплата — чт %02d:00, "
        "обнуление недели — пн 00:00",
        config.survey_hour, config.survey_minute, config.payout_hour,
    )

    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
