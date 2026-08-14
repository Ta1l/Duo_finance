"""Работа с датами и учётными неделями (все расчёты — в МСК)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
REPORTING_START_DATE = date(2026, 8, 10)


def now_msk() -> datetime:
    return datetime.now(tz=MSK)


def today_msk() -> date:
    return now_msk().date()


def week_bounds(day: date) -> tuple[date, date]:
    """Границы учётной недели (Пн 00:00 — Вс 23:59) для произвольной даты."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def editable_report_days(today: date) -> list[date]:
    """Даты текущей недели, которые уже наступили и доступны для ввода."""
    if today < REPORTING_START_DATE:
        return []
    monday, _ = week_bounds(today)
    first_day = max(monday, REPORTING_START_DATE)
    return [
        first_day + timedelta(days=offset)
        for offset in range((today - first_day).days + 1)
    ]


def report_day_number(day: date) -> int:
    """Сквозной номер дня, где 10.08.2026 считается днём 1."""
    if day < REPORTING_START_DATE:
        raise ValueError("Дата раньше начала учёта")
    return (day - REPORTING_START_DATE).days + 1


def previous_week_bounds(day: date) -> tuple[date, date]:
    """Границы недели, предшествующей неделе `day`."""
    monday, _ = week_bounds(day)
    return monday - timedelta(days=7), monday - timedelta(days=1)


def week_key(day: date) -> str:
    """Ключ ISO-недели (для идемпотентности рассылок), напр. '2026-W31'."""
    monday, _ = week_bounds(day)
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def next_payout_date(day: date) -> date:
    """
    Дата выплаты «в пути» для заработка недели `day`:
    четверг следующей недели (4-й день после воскресенья).
    """
    monday, _ = week_bounds(day)
    return monday + timedelta(days=10)
