"""Сборка текстов сообщений: сводка дня, личный статус."""
from __future__ import annotations

from datetime import date

from database.models import DailyReport, User
from services.calculations import eta_days, fmt_eta, fmt_money

WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def daily_summary_text(
    *,
    day: date,
    report: DailyReport,
    user: User,
    prev_streak: int,
    prev_debt: float,
    debt_skipped: bool = False,
) -> str:
    """Сообщение-подтверждение после сохранения ежедневного отчёта."""
    debt_value = (
        "0 ₽ (пропущено)" if debt_skipped and report.debt_paid == 0
        else fmt_money(report.debt_paid)
    )
    lines = [
        f"✅ <b>Отчёт за {day:%d.%m.%Y} ({WD_SHORT[day.weekday()]}) сохранён!</b>",
        "",
        f"💵 Приход на карту: <b>{fmt_money(report.income_card)}</b>",
        f"🧾 Расходы за день: <b>{fmt_money(report.expenses)}</b>",
        f"🛣 В пути (копилка): <b>+{fmt_money(report.in_transit_earned)}</b>",
        f"💳 В счёт долга: <b>{debt_value}</b>",
        "",
    ]
    if prev_debt > 0 and user.debt_current <= 0:
        lines.append("🎉🎉🎉 <b>ДОЛГ ПОЛНОСТЬЮ ПОГАШЕН!</b> Свобода!")
    else:
        lines.append(f"💳 Остаток долга: <b>{fmt_money(user.debt_current)}</b>")

    if report.in_transit_earned > 0:
        lines.append(f"🔥 Стрик копилки: <b>{user.streak_days} дн.</b> — так держать!")
    elif prev_streak > 0:
        lines.append(
            f"💨 Стрик копилки прерван (был {prev_streak} дн.): сегодня 0 ₽ «в пути»."
        )
    else:
        lines.append("🔥 Стрик копилки: 0 дн.")
    return "\n".join(lines)


def status_text(
    *,
    user: User,
    week: dict[str, float],
    avg_payment: float,
    payout_day: date,
    window: int,
    monday: date,
    sunday: date,
) -> str:
    """Личная карточка /status."""
    eta = eta_days(user.debt_current, avg_payment)
    closed = max(0.0, user.debt_start - user.debt_current)
    progress = (closed / user.debt_start * 100.0) if user.debt_start > 0 else 0.0
    return "\n".join(
        [
            f"📊 <b>{user.display_name}</b>, твои показатели:",
            "",
            f"💳 Долг: <b>{fmt_money(user.debt_current)}</b> из "
            f"{fmt_money(user.debt_start)} (закрыто {progress:.0f}%)",
            f"🛣 Копилка «в пути» за неделю {monday:%d.%m}–{sunday:%d.%m}: "
            f"<b>{fmt_money(week['transit'])}</b> (заполнено дней: {week['days']})",
            f"💸 Выплата копилки: <b>{payout_day:%d.%m.%Y}</b> (четверг)",
            f"🔥 Стрик копилки: {user.streak_days} дн.",
            f"🧾 В долг за {window} дн. в среднем: {fmt_money(avg_payment)} / день",
            f"⏳ Прогноз свободы: <b>{fmt_eta(eta)}</b>",
        ]
    )
