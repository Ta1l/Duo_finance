"""Воскресный соревновательный отчёт + барьерная синхронизация двух игроков."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from database import crud
from database.models import User
from services.calculations import avg_over_days, eta_days, fmt_eta, fmt_money
from services.dates import today_msk, week_bounds, week_key

log = logging.getLogger(__name__)

# Barrier Lock: гарантирует однократную генерацию отчёта при одновременной
# отправке воскресных форм двумя игроками.
_barrier_lock = asyncio.Lock()


@dataclass
class PlayerWeek:
    user: User
    income: float           # сумма income_card за Пн–Вс
    expenses: float         # сумма expenses за Пн–Вс
    transit: float          # transit_pool_week (Пн–Вс)
    debt_paid_week: float   # сумма debt_paid за Пн–Вс
    avg_debt_payment: float # средний платёж в долг за окно N дней
    eta: int | None         # прогноз свободы, дни (None — не определён)


def _nomination_line(
    emoji: str,
    title: str,
    a_name: str,
    va: float,
    b_name: str,
    vb: float,
    *,
    higher_wins: bool = True,
) -> str:
    if va == vb:
        winner = "🤝 Ничья"
    elif (va > vb) == higher_wins:
        winner = f"🥇 {a_name}"
    else:
        winner = f"🥇 {b_name}"
    return (
        f"{emoji} <b>«{title}»</b>: {winner}\n"
        f"    <i>{a_name} — {fmt_money(va)} · {b_name} — {fmt_money(vb)}</i>"
    )


def _avg_line(pw: "_PlayerWeekFull") -> str:
    return (
        f"👤 <b>{pw.name}</b>: день стоил {fmt_money(pw.avg_expenses)} · "
        f"копилка +{fmt_money(pw.avg_transit)} · на карту {fmt_money(pw.avg_income)}"
    )


def _debt_line(pw: "_PlayerWeekFull") -> str:
    return (
        f"👤 <b>{pw.name}</b>: в долг за неделю {fmt_money(pw.debt_paid_week)} · "
        f"остаток {fmt_money(pw.user.debt_current)} · "
        f"платёж {fmt_money(pw.avg_debt_payment)}/день · "
        f"свобода: <b>{fmt_eta(pw.eta)}</b>"
    )


# Расширяем датакласс производными «средними за день» (ТЗ: сумма / 7)
@dataclass
class _PlayerWeekFull(PlayerWeek):
    name: str = ""

    @property
    def avg_income(self) -> float:
        return avg_over_days(self.income, 7)

    @property
    def avg_expenses(self) -> float:
        return avg_over_days(self.expenses, 7)

    @property
    def avg_transit(self) -> float:
        return avg_over_days(self.transit, 7)


async def _collect_player_week(
    session: AsyncSession, *, user: User, monday: date, sunday: date, config: Config
) -> _PlayerWeekFull:
    totals = await crud.week_totals(session, user.id, monday, sunday)
    window_end = today_msk()
    window_start = window_end - timedelta(days=config.eta_window_days - 1)
    paid_window = await crud.sum_between(
        session, user.id, "debt_paid", window_start, window_end
    )
    avg_payment = avg_over_days(paid_window, config.eta_window_days)
    return _PlayerWeekFull(
        user=user,
        income=totals["income_card"],
        expenses=totals["expenses"],
        transit=totals["transit"],
        debt_paid_week=totals["debt_paid"],
        avg_debt_payment=avg_payment,
        eta=eta_days(user.debt_current, avg_payment),
        name=escape(user.display_name),
    )


async def build_weekly_report(
    session: AsyncSession, *, players: list[User], sunday: date, config: Config
) -> str:
    """Текст соревновательного отчёта (одинаков для обоих — честная игра)."""
    monday, _ = week_bounds(sunday)
    pa, pb = [
        await _collect_player_week(session, user=p, monday=monday, sunday=sunday, config=config)
        for p in players[:2]
    ]

    nominations = [
        _nomination_line("🏆", "Мастер Заработка", pa.name, pa.transit, pb.name, pb.transit),
        _nomination_line("💳", "Мастер Карты", pa.name, pa.income, pb.name, pb.income),
        _nomination_line(
            "🛡️", "Бережливый года", pa.name, pa.expenses, pb.name, pb.expenses,
            higher_wins=False,
        ),
    ]

    return "\n".join(
        [
            f"🏁 <b>ИТОГИ НЕДЕЛИ {monday:%d.%m} — {sunday:%d.%m}</b>",
            "",
            "🏅 <b>НОМИНАЦИИ НЕДЕЛИ</b>",
            *nominations,
            "",
            "📊 <b>СРЕДНИЕ ПОКАЗАТЕЛИ ЗА ДЕНЬ (за 7 дней)</b>",
            _avg_line(pa),
            _avg_line(pb),
            "",
            "🧾 <b>ДОЛГ И СВОБОДА</b>",
            _debt_line(pa),
            _debt_line(pb),
            "",
            f"🔥 Стрики копилки: {pa.name} — {pa.user.streak_days} дн. · "
            f"{pb.name} — {pb.user.streak_days} дн.",
            "<i>Понедельник — новый отсчёт недели. Вперёд! 💪</i>",
        ]
    )


async def maybe_send_weekly_report(
    bot: Bot,
    session: AsyncSession,
    *,
    user: User,
    report_date: date,
    config: Config,
) -> tuple[str, str | None]:
    """
    Барьерная синхронизация (воскресенье):
    - отчёт не за воскресенье  -> ("not_sunday", None)
    - пары нет                 -> ("no_partner", None)
    - партнёр ещё не заполнил  -> ("waiting", partner_name)
    - оба заполнили            -> генерируем и шлём отчёт обоим -> ("sent", None)
    - уже отправляли           -> ("already_sent", None)
    """
    if report_date.weekday() != 6:  # 6 == воскресенье
        return "not_sunday", None

    async with _barrier_lock:
        partner = await crud.get_partner(session, user)
        if partner is None:
            return "no_partner", None

        partner_report = await crud.get_report(session, partner.id, report_date)
        if partner_report is None:
            log.info(
                "Воскресный барьер: %s заполнил, ждём %s",
                user.display_name, partner.display_name,
            )
            return "waiting", escape(partner.display_name)

        key = f"weekly_report:{week_key(report_date)}"
        if await crud.meta_get(session, key):
            return "already_sent", None
        await crud.meta_set(session, key, "1")

        players = await crud.get_players(session)
        if len(players) < 2:
            return "no_partner", None  # pragma: no cover

        text = await build_weekly_report(
            session, players=players, sunday=report_date, config=config
        )
        await session.commit()

        for p in players:
            try:
                await bot.send_message(p.tg_id, text)
            except Exception:  # noqa: BLE001 — не роняем рассылку из-за одного получателя
                log.exception("Не удалось отправить итоги недели: tg_id=%s", p.tg_id)
        log.info("Воскресный отчёт %s разослан обоим игрокам", key)
        return "sent", None
