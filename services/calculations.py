"""Расчётный модуль: формулы из ТЗ (ETA, средние) и форматирование сумм."""
from __future__ import annotations

import math


def avg_over_days(total: float, days: int) -> float:
    """Средне-дневное значение: сумма / N календарных дней (по ТЗ делим на N всегда)."""
    if days <= 0:
        return 0.0
    return total / days


def eta_days(debt_current: float, avg_daily_payment: float) -> int | None:
    """
    Прогноз полной свободы от долга (в днях, округление вверх):
    - None  -> «не определено» (нет регулярных выплат, avg <= 0)
    - 0     -> долг уже закрыт
    """
    if debt_current <= 0:
        return 0
    if avg_daily_payment <= 0:
        return None
    return math.ceil(debt_current / avg_daily_payment)


def fmt_money(value: float) -> str:
    """12 500 ₽ / 1 234,50 ₽ (русский формат: пробел-тысячи, запятая-разделитель)."""
    if float(value).is_integer():
        return f"{int(value):,} ₽".replace(",", " ")
    return f"{float(value):,.2f} ₽".replace(",", " ").replace(".", ",")


def fmt_eta(days: int | None) -> str:
    if days is None:
        return "не определён (нет регулярных выплат)"
    if days <= 0:
        return "долг закрыт 🎉"
    return f"~{days} дн. (~{days / 30.44:.1f} мес.)"
