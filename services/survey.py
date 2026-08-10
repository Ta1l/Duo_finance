"""Запуск ежедневного опроса из планировщика (вне контекста хендлера)."""
from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from database.models import User
from handlers.states import DailyForm

log = logging.getLogger(__name__)

WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

STEP1_TEXT = (
    "Шаг 1/4: Сколько денег упало на карту за сегодня? (руб.)\n"
    "<i>Введи число ≥ 0, например: 1500 или 2450.50 · /cancel — отмена.</i>"
)


def survey_intro_text(day: date) -> str:
    return (
        f"🌙 <b>Вечерний отчёт за {day:%d.%m.%Y} ({WD_SHORT[day.weekday()]})</b>\n\n"
        + STEP1_TEXT
    )


async def begin_daily_survey(
    bot: Bot,
    storage: BaseStorage,
    *,
    bot_id: int,
    user: User,
    day: date,
) -> None:
    """
    Ставит пользователю FSM-состояние income_card и отправляет первый вопрос.
    Используется планировщиком в 23:30 МСК (и допускает перезапуск потока).
    """
    key = StorageKey(bot_id=bot_id, chat_id=user.tg_id, user_id=user.tg_id)
    state = FSMContext(storage=storage, key=key)
    await state.clear()
    await state.update_data(report_date=day.isoformat())
    await state.set_state(DailyForm.income_card)
    await bot.send_message(user.tg_id, survey_intro_text(day))
    log.info("Ежедневный опрос отправлен: %s (tg_id=%s)", user.display_name, user.tg_id)
