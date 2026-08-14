from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.states import DailyForm
from services.survey import begin_daily_survey


class ScheduledSurveyTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.storage = MemoryStorage()
        self.bot_id = 99
        self.user = SimpleNamespace(tg_id=101, display_name="Tester")
        self.key = StorageKey(
            bot_id=self.bot_id,
            chat_id=self.user.tg_id,
            user_id=self.user.tg_id,
        )

    async def asyncTearDown(self) -> None:
        await self.storage.close()

    async def test_successful_prompt_starts_report_for_requested_day(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())

        await begin_daily_survey(
            bot,
            self.storage,
            bot_id=self.bot_id,
            user=self.user,
            day=date(2026, 8, 14),
        )

        state = FSMContext(storage=self.storage, key=self.key)
        self.assertEqual(await state.get_state(), DailyForm.income_card.state)
        self.assertEqual(await state.get_data(), {"report_date": "2026-08-14"})

    async def test_failed_prompt_does_not_leave_hidden_active_state(self) -> None:
        bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=RuntimeError("network error"))
        )

        with self.assertRaises(RuntimeError):
            await begin_daily_survey(
                bot,
                self.storage,
                bot_id=self.bot_id,
                user=self.user,
                day=date(2026, 8, 14),
            )

        state = FSMContext(storage=self.storage, key=self.key)
        self.assertIsNone(await state.get_state())
        self.assertEqual(await state.get_data(), {})
