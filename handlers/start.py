"""Регистрация пары (/start), /status, /help и вежливый fallthrough."""
from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from database import crud
from database.models import User
from services.calculations import avg_over_days
from services.dates import next_payout_date, today_msk, week_bounds
from services.render import status_text

log = logging.getLogger(__name__)
router = Router(name="start")

PLAYERS_LIMIT = 2

HELP_TEXT = (
    "🤖 <b>Дуэт-финансист</b> — бот парного учёта: гасим долги наперегонки.\n\n"
    "<b>Команды:</b>\n"
    "/report — заполнить отчёт за сегодня вручную\n"
    "/editday — внести или изменить отчёт за день текущей недели\n"
    "/status — мои текущие показатели\n"
    "/cancel — прервать текущий опрос\n"
    "/help — эта справка\n\n"
    "<b>Расписание (МСК):</b>\n"
    "• опрос за день — ежедневно в 23:30\n"
    "• выплата копилки «в пути» — по четвергам в 09:00\n"
    "• соревновательные итоги недели — в воскресенье, "
    "как только оба заполнили отчёт\n"
    "• понедельник 00:00 — старт новой учётной недели"
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    db_user: User | None,
    config: Config,
) -> None:
    assert message.from_user is not None

    if db_user is not None:
        await message.answer(
            f"С возвращением, <b>{db_user.display_name}</b> (слот {db_user.slot})! 👋\n"
            f"Остаток долга: <b>{db_user.debt_current:,.0f} ₽</b>\n\n"
            "Показатели — /status, отчёт за день — /report, справка — /help."
        )
        return

    players_count = await crud.count_players(session)
    if players_count >= PLAYERS_LIMIT:
        await message.answer(
            "🚫 Оба слота уже заняты. Это приватный бот строго для двух игроков."
        )
        log.warning("Отказ в регистрации (слоты заняты): tg_id=%s", message.from_user.id)
        return

    slot = "A" if players_count == 0 else "B"
    user = await crud.create_user(
        session,
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
        slot=slot,
        start_debt=config.start_debt,
    )
    await session.commit()

    await message.answer(
        f"🎮 Привет, <b>{user.display_name}</b>! Ты — <b>Игрок {slot}</b>.\n"
        f"Стартовый долг зафиксирован: <b>{config.start_debt:,.0f} ₽</b>.\n\n"
        "Каждый день в 23:30 МСК я буду спрашивать: приход на карту, расходы, "
        "копилку «в пути» и платёж в долг. Вопросы можно заполнить и раньше — /report."
    )
    log.info("Зарегистрирован игрок %s: %s (tg_id=%s)", slot, user.display_name, user.tg_id)

    if slot == "B":
        players = await crud.get_players(session)
        greet = (
            "🎉 <b>Пара собрана!</b> Игра началась: ежедневные отчёты в 23:30, "
            "воскресные баттлы и кто быстрее закроет долг. Удачи обоим! 💪"
        )
        for p in players:
            try:
                await message.bot.send_message(p.tg_id, greet)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось уведомить tg_id=%s о сборе пары", p.tg_id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    session: AsyncSession,
    db_user: User,
    config: Config,
) -> None:
    today = today_msk()
    monday, sunday = week_bounds(today)
    week = await crud.week_totals(session, db_user.id, monday, sunday)
    window_start = today - timedelta(days=config.eta_window_days - 1)
    paid = await crud.sum_between(session, db_user.id, "debt_paid", window_start, today)
    avg_payment = avg_over_days(paid, config.eta_window_days)
    await message.answer(
        status_text(
            user=db_user,
            week=week,
            avg_payment=avg_payment,
            payout_day=next_payout_date(today),
            window=config.eta_window_days,
            monday=monday,
            sunday=sunday,
        )
    )


@router.message(StateFilter(None))
async def fallback(message: Message) -> None:
    await message.answer(
        "👋 Я понимаю команды:\n"
        "/report — отчёт за день\n"
        "/editday — отчёт за день текущей недели\n"
        "/status — мои показатели\n"
        "/help — справка"
    )
