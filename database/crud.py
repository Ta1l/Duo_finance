"""CRUD-операции и агрегации. Все функции принимают открытую AsyncSession."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DailyReport, MetaKV, User


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

async def get_by_tg(session: AsyncSession, tg_id: int) -> User | None:
    return await session.scalar(select(User).where(User.tg_id == tg_id))


async def count_players(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(User.id))) or 0)


async def create_user(
    session: AsyncSession,
    *,
    tg_id: int,
    username: str | None,
    first_name: str,
    slot: str,
    start_debt: float,
) -> User:
    user = User(
        tg_id=tg_id,
        username=username,
        first_name=first_name,
        slot=slot,
        debt_start=start_debt,
        debt_current=start_debt,
        streak_days=0,
    )
    session.add(user)
    await session.flush()
    return user


async def get_players(session: AsyncSession) -> list[User]:
    """Оба игрока пары, упорядоченные по слоту."""
    return list((await session.scalars(select(User).order_by(User.slot))).all())


async def get_partner(session: AsyncSession, user: User) -> User | None:
    return await session.scalar(select(User).where(User.id != user.id).limit(1))


# ---------------------------------------------------------------------------
# Ежедневные отчёты
# ---------------------------------------------------------------------------

async def get_report(session: AsyncSession, user_id: int, day: date) -> DailyReport | None:
    return await session.scalar(
        select(DailyReport).where(
            DailyReport.user_id == user_id,
            DailyReport.report_date == day,
        )
    )


async def get_reports_between(
    session: AsyncSession, user_id: int, date_from: date, date_to: date
) -> list[DailyReport]:
    """Отчёты пользователя за диапазон дат, отсортированные по дате."""
    reports = await session.scalars(
        select(DailyReport)
        .where(
            DailyReport.user_id == user_id,
            DailyReport.report_date >= date_from,
            DailyReport.report_date <= date_to,
        )
        .order_by(DailyReport.report_date)
    )
    return list(reports.all())


async def upsert_report(
    session: AsyncSession,
    *,
    user_id: int,
    day: date,
    income_card: float,
    expenses: float,
    in_transit_earned: float,
    debt_paid: float,
) -> DailyReport:
    """Создаёт отчёт за день или перезаписывает существующий."""
    report = await get_report(session, user_id, day)
    if report is None:
        report = DailyReport(user_id=user_id, report_date=day)
        session.add(report)
    report.income_card = income_card
    report.expenses = expenses
    report.in_transit_earned = in_transit_earned
    report.debt_paid = debt_paid
    await session.flush()
    return report


async def recompute_debt(session: AsyncSession, user: User) -> float:
    """
    Формула: debt_current = debt_start - Σ(debt_paid) по всей истории, не ниже 0.

    Эквивалентна инкрементальной debt_current = debt_previous - debt_paid,
    но устойчива к перезаписи отчётов (пересчёт от источника истины).
    """
    total_paid = await session.scalar(
        select(func.coalesce(func.sum(DailyReport.debt_paid), 0.0)).where(
            DailyReport.user_id == user.id
        )
    )
    user.debt_current = max(0.0, round(user.debt_start - float(total_paid), 2))
    await session.flush()
    return user.debt_current


async def recalc_streak(session: AsyncSession, user: User, anchor: date) -> int:
    """
    Стрик = количество дней подряд (заканчивая anchor-датой),
    когда in_transit_earned > 0. Пропуск дня (нет отчёта) или 0 руб. — разрыв.
    """
    rows = await session.scalars(
        select(DailyReport.report_date).where(
            DailyReport.user_id == user.id,
            DailyReport.report_date <= anchor,
            DailyReport.in_transit_earned > 0,
        )
    )
    positive: set[date] = set(rows.all())
    streak = 0
    day = anchor
    while day in positive:
        streak += 1
        day -= timedelta(days=1)
    user.streak_days = streak
    await session.flush()
    return streak


async def recalc_current_streak(
    session: AsyncSession, user: User, today: date
) -> int:
    """Пересчитывает стрик до последнего заполненного дня, не позднее сегодня."""
    latest_day = await session.scalar(
        select(func.max(DailyReport.report_date)).where(
            DailyReport.user_id == user.id,
            DailyReport.report_date <= today,
        )
    )
    if latest_day is None:
        user.streak_days = 0
        await session.flush()
        return 0
    return await recalc_streak(session, user, latest_day)


# ---------------------------------------------------------------------------
# Агрегации
# ---------------------------------------------------------------------------

async def sum_between(
    session: AsyncSession, user_id: int, column: str, date_from: date, date_to: date
) -> float:
    """Сумма любого денежного поля отчётов за произвольный диапазон дат."""
    col = getattr(DailyReport, column)
    value = await session.scalar(
        select(func.coalesce(func.sum(col), 0.0)).where(
            DailyReport.user_id == user_id,
            DailyReport.report_date >= date_from,
            DailyReport.report_date <= date_to,
        )
    )
    return float(value or 0.0)


async def week_totals(
    session: AsyncSession, user_id: int, monday: date, sunday: date
) -> dict[str, float]:
    """Суммы недели (Пн–Вс): transit_pool_week и остальные показатели."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(DailyReport.income_card), 0.0),
                func.coalesce(func.sum(DailyReport.expenses), 0.0),
                func.coalesce(func.sum(DailyReport.in_transit_earned), 0.0),
                func.coalesce(func.sum(DailyReport.debt_paid), 0.0),
                func.count(DailyReport.id),
            ).where(
                DailyReport.user_id == user_id,
                DailyReport.report_date >= monday,
                DailyReport.report_date <= sunday,
            )
        )
    ).one()
    income, expenses, transit, debt, days = row
    return {
        "income_card": float(income),
        "expenses": float(expenses),
        "transit": float(transit),  # == transit_pool_week
        "debt_paid": float(debt),
        "days": int(days),
    }


# ---------------------------------------------------------------------------
# Служебные ключи (идемпотентность рассылок)
# ---------------------------------------------------------------------------

async def meta_get(session: AsyncSession, key: str) -> str | None:
    row = await session.get(MetaKV, key)
    return row.value if row else None


async def meta_set(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(MetaKV, key)
    if row is None:
        session.add(MetaKV(key=key, value=value))
    else:
        row.value = value
    await session.flush()
