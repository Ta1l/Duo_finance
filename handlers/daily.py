"""FSM-флоу ежедневного отчёта (шаги 1–4), /report, /cancel, перезапись отчёта."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import Config
from database import crud
from database.models import User
from handlers.states import DailyForm
from keyboards.common import is_skip_text, overwrite_keyboard, skip_keyboard
from services.calculations import fmt_money
from services.dates import parse_date, today_msk
from services.render import daily_summary_text
from services.survey import STEP1_TEXT, survey_intro_text
from services.validation import parse_amount
from services.weekly_report import maybe_send_weekly_report
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)
router = Router(name="daily")

Q_EXPENSES = "Шаг 2/4: Сколько денег ты потратил за этот день? (руб.)"
Q_TRANSIT = (
    "Шаг 3/4: Сколько заработал «в пути» за этот день "
    "(к выплате в следующий четверг)? (руб.)"
)
Q_DEBT = (
    "Шаг 4/4: Сколько внёс в счёт погашения долга за этот день? (руб.)\n"
    "<i>Сумма ≥ 0 или нажми «Пропустить (0)».</i>"
)
Q_EDITDAY_DATE = (
    "Введите дату, за которую хотите изменить данные, в формате ДД.ММ.ГГГГ, "
    "например 04.06.2026."
)
ERR_DATE_FORMAT = (
    "⚠️ Неверный формат даты. Введите её в виде ДД.MM.ГГГГ, например 04.06.2026."
)
ERR_DATE_FUTURE = (
    "⚠️ Нельзя менять данные за будущую дату. Введите дату сегодня или раньше."
)
ERR_AMOUNT = (
    "⚠️ Нужно неотрицательное число в рублях.\n"
    "Примеры: 0, 500, 1250.75. Попробуй ещё раз:"
)


# ---------------------------------------------------------------------------
# Завершение опроса: сохранение + пересчёты + воскресный барьер
# ---------------------------------------------------------------------------

def _format_report_preview(day: date, report: Any) -> str:
    if report is None:
        return (
            f"За {day:%d.%m.%Y} данных нет. Начнём новый отчёт за этот день."
        )
    return (
        f"За {day:%d.%m.%Y} уже есть данные:\n"
        f"💵 Приход: {fmt_money(report.income_card)} · "
        f"🧾 Расходы: {fmt_money(report.expenses)}\n"
        f"🛣 В пути: {fmt_money(report.in_transit_earned)} · "
        f"💳 В долг: {fmt_money(report.debt_paid)}"
    )


async def _finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    config: Config,
    *,
    debt_paid: float,
    debt_skipped: bool,
) -> None:
    data = await state.get_data()
    raw_day = data.get("report_date")
    report_day = date.fromisoformat(raw_day) if raw_day else today_msk()

    prev_streak = db_user.streak_days
    prev_debt = db_user.debt_current

    report = await crud.upsert_report(
        session,
        user_id=db_user.id,
        day=report_day,
        income_card=float(data.get("income_card", 0.0)),
        expenses=float(data.get("expenses", 0.0)),
        in_transit_earned=float(data.get("in_transit_earned", 0.0)),
        debt_paid=debt_paid,
    )
    # Пересчёт накопительных показателей от источника истины
    await crud.recompute_debt(session, db_user)
    await crud.recalc_streak(session, db_user, report_day)
    await session.commit()
    await state.clear()

    await message.answer(
        daily_summary_text(
            day=report_day,
            report=report,
            user=db_user,
            prev_streak=prev_streak,
            prev_debt=prev_debt,
            debt_skipped=debt_skipped,
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    log.info(
        "Отчёт сохранён: %s за %s (долг: %.2f, стрик: %s)",
        db_user.display_name, report_day, db_user.debt_current, db_user.streak_days,
    )

    # Воскресная барьерная синхронизация: ждём второго игрока или шлём итоги
    status, partner_name = await maybe_send_weekly_report(
        bot, session, user=db_user, report_date=report_day, config=config
    )
    if status == "waiting":
        await message.answer(
            f"⏳ Твой отчёт зафиксирован! Ждём, пока <b>{partner_name}</b> заполнит "
            "данные, чтобы подвести честные итоги недели…"
        )
    elif status == "sent":
        await message.answer("🏁 Оба отчёта на месте — итоги недели выше 👆")


# ---------------------------------------------------------------------------
# Команды: /cancel (прерывание), /report (ручной запуск / перезапись)
# ---------------------------------------------------------------------------

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Сейчас нет активного опроса — всё чисто 👌")
        return
    await state.clear()
    await message.answer(
        "Опрос отменён, ничего не сохранено. Начать заново — /report.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("editday"))
async def cmd_edit_day(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    if await state.get_state() is not None:
        await state.clear()

    await state.set_state(DailyForm.date_selection)
    await message.answer(Q_EDITDAY_DATE)


@router.message(DailyForm.date_selection)
async def step_edit_day_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    report_day = parse_date(message.text)
    if report_day is None:
        await message.answer(ERR_DATE_FORMAT)
        return

    if report_day > today_msk():
        await message.answer(ERR_DATE_FUTURE)
        return

    existing = await crud.get_report(session, db_user.id, report_day)
    await message.answer(_format_report_preview(report_day, existing))

    await state.update_data(report_date=report_day.isoformat())
    await state.set_state(DailyForm.income_card)
    await message.answer(survey_intro_text(report_day))


@router.message(Command("report"))
async def cmd_report(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    today = today_msk()
    if await state.get_state() is not None:
        # Уже в процессе — просто перезапускаем поток за сегодня
        await state.clear()
    else:
        existing = await crud.get_report(session, db_user.id, today)
        if existing is not None:
            await message.answer(
                f"ℹ️ Отчёт за {today:%d.%m.%Y} уже заполнен:\n"
                f"💵 Приход: {fmt_money(existing.income_card)} · "
                f"🧾 Расходы: {fmt_money(existing.expenses)}\n"
                f"🛣 В пути: {fmt_money(existing.in_transit_earned)} · "
                f"💳 В долг: {fmt_money(existing.debt_paid)}\n\n"
                "Перезаписать его?",
                reply_markup=overwrite_keyboard(),
            )
            return

    await state.set_state(DailyForm.income_card)
    await state.update_data(report_date=today.isoformat())
    await message.answer(survey_intro_text(today))


@router.callback_query(F.data == "survey:overwrite")
async def cb_overwrite(cb: CallbackQuery, state: FSMContext) -> None:
    today = today_msk()
    await state.set_state(DailyForm.income_card)
    await state.update_data(report_date=today.isoformat())
    if cb.message is not None:
        await cb.message.edit_text(
            f"🔄 Заполняем заново отчёт за {today:%d.%m.%Y}.\n\n{STEP1_TEXT}"
        )
    await cb.answer()


@router.callback_query(F.data == "survey:dismiss")
async def cb_dismiss(cb: CallbackQuery) -> None:
    if cb.message is not None:
        await cb.message.edit_text("Ок, оставляем прежний отчёт ✅")
    await cb.answer()


# ---------------------------------------------------------------------------
# FSM-шаги
# ---------------------------------------------------------------------------

@router.message(DailyForm.income_card)
async def step_income_card(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(ERR_AMOUNT)
        return
    await state.update_data(income_card=amount)
    await state.set_state(DailyForm.expenses)
    await message.answer(Q_EXPENSES)


@router.message(DailyForm.expenses)
async def step_expenses(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(ERR_AMOUNT)
        return
    await state.update_data(expenses=amount)
    await state.set_state(DailyForm.in_transit_earned)
    await message.answer(Q_TRANSIT)


@router.message(DailyForm.in_transit_earned)
async def step_in_transit(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(ERR_AMOUNT)
        return
    await state.update_data(in_transit_earned=amount)
    await state.set_state(DailyForm.debt_paid)
    await message.answer(Q_DEBT, reply_markup=skip_keyboard())


@router.message(DailyForm.debt_paid, F.text.func(is_skip_text))
async def step_debt_skip(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    config: Config,
) -> None:
    """Кнопка/текст «Пропустить (0)»: debt_paid = 0, остаток долга не меняется."""
    await _finish(
        message, state, session, db_user, bot, config,
        debt_paid=0.0, debt_skipped=True,
    )


@router.message(DailyForm.debt_paid)
async def step_debt_paid(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    config: Config,
) -> None:
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(ERR_AMOUNT, reply_markup=skip_keyboard())
        return
    await _finish(
        message, state, session, db_user, bot, config,
        debt_paid=amount, debt_skipped=False,
    )
