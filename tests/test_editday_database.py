from __future__ import annotations

from datetime import date
from unittest import IsolatedAsyncioTestCase

from database import crud
from database.engine import init_models, make_engine, make_session_factory


class EditDayDatabaseTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_models(self.engine)
        self.pool = make_session_factory(self.engine)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_missing_days_can_be_added_and_existing_days_replaced(self) -> None:
        async with self.pool() as session:
            user = await crud.create_user(
                session,
                tg_id=1,
                username="player",
                first_name="Player",
                slot="A",
                start_debt=10_000,
            )
            await crud.upsert_report(
                session,
                user_id=user.id,
                day=date(2026, 8, 10),
                income_card=1000,
                expenses=200,
                in_transit_earned=300,
                debt_paid=500,
            )
            await crud.upsert_report(
                session,
                user_id=user.id,
                day=date(2026, 8, 11),
                income_card=2000,
                expenses=400,
                in_transit_earned=600,
                debt_paid=1000,
            )
            await crud.upsert_report(
                session,
                user_id=user.id,
                day=date(2026, 8, 10),
                income_card=1500,
                expenses=250,
                in_transit_earned=350,
                debt_paid=750,
            )
            await crud.recompute_debt(session, user)
            await crud.recalc_streak(session, user, date(2026, 8, 11))
            await session.commit()

            reports = await crud.get_reports_between(
                session, user.id, date(2026, 8, 10), date(2026, 8, 14)
            )

            self.assertEqual(len(reports), 2)
            self.assertEqual(reports[0].income_card, 1500)
            self.assertEqual(user.debt_current, 8250)
            self.assertEqual(user.streak_days, 2)

    async def test_past_edit_recalculates_streak_to_latest_report(self) -> None:
        async with self.pool() as session:
            user = await crud.create_user(
                session,
                tg_id=2,
                username="player2",
                first_name="Player 2",
                slot="B",
                start_debt=10_000,
            )
            for day in range(10, 15):
                await crud.upsert_report(
                    session,
                    user_id=user.id,
                    day=date(2026, 8, day),
                    income_card=100,
                    expenses=0,
                    in_transit_earned=100,
                    debt_paid=0,
                )

            await crud.upsert_report(
                session,
                user_id=user.id,
                day=date(2026, 8, 12),
                income_card=100,
                expenses=0,
                in_transit_earned=0,
                debt_paid=0,
            )
            await crud.recalc_current_streak(session, user, date(2026, 8, 14))

            self.assertEqual(user.streak_days, 2)
