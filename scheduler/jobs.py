"""Фоновые задачи APScheduler (все времена — МСК).

- 23:30 ежедневно   — рассылка ежедневного опроса
- четверг 09:00     — уведомление о выплате копилки «в пути» за прошлую неделю
- понедельник 00:00 — обнуление недельной копилки (старт новой учётной недели)
"""
from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from aiogram.fsm.storage.base import BaseStorage

from config import Config
from database import crud
from database.models import User
from services.calculations import fmt_money
from services.dates import MSK, now_msk, week_bounds, week_key
from services.survey import begin_daily_survey

log = logging.getLogger(__name__)


def setup_scheduler(
    *,
    bot: Bot,
    bot_id: int,
    dp_storage: BaseStorage,
    session_pool: async_sessionmaker[AsyncSession],
    config: Config,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MSK)

    # 23:30 МСК каждый день — опрос за день
    scheduler.add_job(
        job_daily_survey,
        CronTrigger(
            hour=config.survey_hour, minute=config.survey_minute, timezone=MSK
        ),
        args=[bot, bot_id, dp_storage, session_pool, config],
        id="daily_survey",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Четверг 09:00 МСК — выплата «в пути» за прошлую неделю
    scheduler.add_job(
        job_thursday_payout,
        CronTrigger(day_of_week="thu", hour=config.payout_hour, minute=0, timezone=MSK),
        args=[bot, session_pool],
        id="thursday_payout",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Понедельник 00:00 МСК — обнуление счётчика недели + пинок мотивации
    scheduler.add_job(
        job_monday_reset,
        CronTrigger(day_of_week="mon", hour=0, minute=0, timezone=MSK),
        args=[bot, session_pool],
        id="monday_reset",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler


async def _players(session: AsyncSession) -> list[User]:
    return await crud.get_players(session)


async def _send_safe(bot: Bot, user: User, text: str) -> None:
    try:
        await bot.send_message(user.tg_id, text)
    except Exception:  # noqa: BLE001 — не роняем джобу из-за одного получателя
        log.exception("Не удалось отправить сообщение tg_id=%s", user.tg_id)


# ---------------------------------------------------------------------------
# 23:30 — ежедневный опрос
# ---------------------------------------------------------------------------

async def job_daily_survey(
    bot: Bot,
    bot_id: int,
    dp_storage: BaseStorage,
    session_pool: async_sessionmaker[AsyncSession],
    config: Config,
) -> None:
    today = now_msk().date()
    async with session_pool() as session:
        players = await _players(session)
        to_prompt: list[User] = []
        for p in players:
            if await crud.get_report(session, p.id, today) is None:
                to_prompt.append(p)  # уже заполнил сегодня (/report) — не тревожим

    log.info("job_daily_survey: опрос отправляется %d из %d игрокам", len(to_prompt), len(players))
    for p in to_prompt:
        try:
            await begin_daily_survey(bot, dp_storage, bot_id=bot_id, user=p, day=today)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось начать опрос для tg_id=%s", p.tg_id)


# ---------------------------------------------------------------------------
# Четверг 09:00 — выплата копилки «в пути» за прошлую неделю (Пн–Вс)
# ---------------------------------------------------------------------------

async def job_thursday_payout(
    bot: Bot, session_pool: async_sessionmaker[AsyncSession]
) -> None:
    today = now_msk().date()
    monday_this, _ = week_bounds(today)
    prev_mon = monday_this - timedelta(days=7)
    prev_sun = monday_this - timedelta(days=1)
    key = f"payout:{week_key(prev_mon)}"

    async with session_pool() as session:
        if await crud.meta_get(session, key):  # идемпотентность (перезапуск бота)
            log.info("job_thursday_payout: %s уже отправлен", key)
            return
        players = await _players(session)
        amounts: list[tuple[User, float]] = []
        for p in players:
            total = await crud.sum_between(
                session, p.id, "in_transit_earned", prev_mon, prev_sun
            )
            amounts.append((p, total))
        await crud.meta_set(session, key, "1")
        await session.commit()

    for p, amount in amounts:
        if amount > 0:
            text = (
                "💸 <b>Сегодня четверг!</b>\n"
                f"Твоя сгораемая копилка за прошлую неделю ({prev_mon:%d.%m}–{prev_sun:%d.%m}) "
                f"превратилась в реальные деньги: <b>+{fmt_money(amount)}</b>! 🎉\n"
                "Не забудь занести её в отчёт, когда придёт на карту."
            )
        else:
            text = (
                "💸 <b>Сегодня четверг!</b>\n"
                "Копилка «в пути» за прошлую неделю пустовала (+0 ₽). "
                "Впереди новая неделя — есть шанс наполнить её! 💪"
            )
        await _send_safe(bot, p, text)


# ---------------------------------------------------------------------------
# Понедельник 00:00 — обнуление недельной копилки
# ---------------------------------------------------------------------------

async def job_monday_reset(
    bot: Bot, session_pool: async_sessionmaker[AsyncSession]
) -> None:
    """
    transit_pool_week считается как Σ(in_transit_earned) за Пн–Вс текущей
    недели прямо из отчётов (единый источник истины), поэтому «обнуление»
    происходит само сменой учётного окна. Джоб фиксирует старт недели
    и шлёт мотивационное уведомление.
    """
    async with session_pool() as session:
        players = await _players(session)

    for p in players:
        await _send_safe(
            bot,
            p,
            "🗓 <b>Понедельник!</b> Новая учётная неделя стартовала — "
            "счётчик копилки «в пути» обнулён (Пн 00:00 — Вс 23:59).\n"
            "Прошлые рекорды соперника записаны. Бьём их! 💪",
        )
