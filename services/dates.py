"""Работа с датами и учётными неделями (все расчёты — в МСК)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(tz=MSK)


def today_msk() -> date:
    return now_msk().date()


def week_bounds(day: date) -> tuple[date, date]:
    """Границы учётной недели (Пн 00:00 — Вс 23:59) для произвольной даты."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


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
