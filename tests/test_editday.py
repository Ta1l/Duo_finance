from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from handlers.daily import (
    Q_EDITDAY_MENU,
    _finish,
    cb_edit_day,
    cb_overwrite,
    cmd_edit_day,
    cmd_report,
    step_expenses,
    step_income_card,
    step_in_transit,
)
from handlers.states import DailyForm
from keyboards.common import edit_day_keyboard
from services.dates import (
    REPORTING_START_DATE,
    editable_report_days,
    report_day_number,
)


class FakeState:
    def __init__(self) -> None:
        self.state = None
        self.data: dict[str, object] = {}

    async def get_state(self):
        return self.state

    async def get_data(self) -> dict[str, object]:
        return self.data.copy()

    async def clear(self) -> None:
        self.state = None
        self.data = {}

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.answers: list[tuple[str, object | None]] = []
        self.edited_text: str | None = None

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str) -> None:
        self.edited_text = text


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=123)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.answer = AsyncMock()


class EditableDatesTests(TestCase):
    def test_first_week_starts_with_day_one_and_stops_today(self) -> None:
        days = editable_report_days(date(2026, 8, 14))
        self.assertEqual(
            days,
            [date(2026, 8, day) for day in range(10, 15)],
        )
        self.assertEqual(report_day_number(days[0]), 1)
        self.assertEqual(report_day_number(days[-1]), 5)

    def test_next_week_only_contains_current_week(self) -> None:
        days = editable_report_days(date(2026, 8, 19))
        self.assertEqual(
            days,
            [date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)],
        )
        self.assertEqual([report_day_number(day) for day in days], [8, 9, 10])

    def test_no_days_before_reporting_start(self) -> None:
        self.assertEqual(editable_report_days(date(2026, 8, 9)), [])
        with self.assertRaises(ValueError):
            report_day_number(REPORTING_START_DATE.replace(day=9))

    def test_keyboard_marks_existing_reports(self) -> None:
        days = editable_report_days(date(2026, 8, 12))
        keyboard = edit_day_keyboard(days, {date(2026, 8, 10)})
        buttons = [row[0] for row in keyboard.inline_keyboard]
        self.assertEqual(buttons[0].text, "✅ День 1 · Пн 10.08")
        self.assertEqual(buttons[1].text, "➕ День 2 · Вт 11.08")
        self.assertEqual(buttons[2].callback_data, "editday:2026-08-12")


class EditDayHandlerTests(IsolatedAsyncioTestCase):
    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    @patch("handlers.daily.crud.get_reports_between", new_callable=AsyncMock)
    async def test_command_returns_current_week_buttons(self, get_reports, _today) -> None:
        get_reports.return_value = [SimpleNamespace(report_date=date(2026, 8, 10))]
        message = FakeMessage("/editday")
        state = FakeState()
        user = SimpleNamespace(id=7)
        session = object()

        await cmd_edit_day(message, state, session=session, db_user=user)

        self.assertEqual(state.state, DailyForm.date_selection)
        text, keyboard = message.answers[-1]
        self.assertEqual(text, Q_EDITDAY_MENU)
        self.assertEqual(len(keyboard.inline_keyboard), 5)
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "✅ День 1 · Пн 10.08")
        get_reports.assert_awaited_once_with(
            session, 7, date(2026, 8, 10), date(2026, 8, 14)
        )

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    @patch("handlers.daily.crud.get_report", new_callable=AsyncMock)
    async def test_day_button_starts_regular_report_flow(self, get_report, _today) -> None:
        get_report.return_value = None
        callback = FakeCallback("editday:2026-08-11")
        state = FakeState()

        await cb_edit_day(
            callback,
            state,
            session=object(),
            db_user=SimpleNamespace(id=7),
        )

        self.assertEqual(state.state, DailyForm.income_card)
        self.assertEqual(
            state.data,
            {"report_date": "2026-08-11", "edit_mode": True},
        )
        self.assertIn("11.08.2026", callback.message.edited_text)
        self.assertIn("Шаг 1/4", callback.message.answers[-1][0])
        callback.answer.assert_awaited_once_with()

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 17))
    async def test_stale_previous_week_button_is_rejected(self, _today) -> None:
        callback = FakeCallback("editday:2026-08-14")
        state = FakeState()

        await cb_edit_day(
            callback,
            state,
            session=object(),
            db_user=SimpleNamespace(id=7),
        )

        self.assertIsNone(state.state)
        callback.answer.assert_awaited_once_with(
            "Этот день уже недоступен. Откройте /editday снова.",
            show_alert=True,
        )

    async def test_selected_day_uses_all_regular_amount_steps(self) -> None:
        state = FakeState()
        await state.set_state(DailyForm.income_card)

        await step_income_card(FakeMessage("1000"), state)
        await step_expenses(FakeMessage("250"), state)
        await step_in_transit(FakeMessage("700"), state)

        self.assertEqual(state.state, DailyForm.debt_paid)
        self.assertEqual(
            state.data,
            {"income_card": 1000.0, "expenses": 250.0, "in_transit_earned": 700.0},
        )

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    @patch("handlers.daily.daily_summary_text", return_value="saved")
    @patch("handlers.daily.maybe_send_weekly_report", new_callable=AsyncMock)
    @patch("handlers.daily.crud.recalc_current_streak", new_callable=AsyncMock)
    @patch("handlers.daily.crud.recompute_debt", new_callable=AsyncMock)
    @patch("handlers.daily.crud.upsert_report", new_callable=AsyncMock)
    async def test_past_edit_recalculates_streak_through_today(
        self,
        upsert_report,
        _recompute_debt,
        recalc_current_streak,
        weekly_report,
        _summary,
        _today,
    ) -> None:
        upsert_report.return_value = SimpleNamespace()
        weekly_report.return_value = ("not_sunday", None)
        state = FakeState()
        state.data = {
            "report_date": "2026-08-10",
            "edit_mode": True,
            "income_card": 1000,
            "expenses": 200,
            "in_transit_earned": 300,
        }
        message = FakeMessage()
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(
            id=7,
            streak_days=4,
            debt_current=9000,
            display_name="Player",
        )

        await _finish(
            message,
            state,
            session,
            user,
            bot=object(),
            config=object(),
            debt_paid=500,
            debt_skipped=False,
        )

        recalc_current_streak.assert_awaited_once_with(
            session, user, date(2026, 8, 14)
        )

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 17))
    @patch("handlers.daily.crud.upsert_report", new_callable=AsyncMock)
    async def test_edit_is_rejected_if_week_changes_before_finish(
        self, upsert_report, _today
    ) -> None:
        state = FakeState()
        state.data = {
            "report_date": "2026-08-14",
            "edit_mode": True,
            "income_card": 1000,
            "expenses": 200,
            "in_transit_earned": 300,
        }
        message = FakeMessage()

        await _finish(
            message,
            state,
            session=SimpleNamespace(),
            db_user=SimpleNamespace(),
            bot=object(),
            config=object(),
            debt_paid=500,
            debt_skipped=False,
        )

        upsert_report.assert_not_awaited()
        self.assertEqual(state.data, {})
        self.assertIn("Неделя уже сменилась", message.answers[-1][0])

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    @patch("handlers.daily.crud.get_report", new_callable=AsyncMock)
    async def test_report_does_not_silently_overwrite_existing_data(
        self, get_report, _today
    ) -> None:
        get_report.return_value = SimpleNamespace(
            income_card=1000,
            expenses=200,
            in_transit_earned=300,
            debt_paid=400,
        )
        state = FakeState()
        state.state = DailyForm.expenses
        state.data = {"income_card": 999}
        message = FakeMessage("/report")

        await cmd_report(
            message,
            state,
            session=object(),
            db_user=SimpleNamespace(id=7),
        )

        self.assertIsNone(state.state)
        self.assertEqual(state.data, {})
        text, keyboard = message.answers[-1]
        self.assertIn("уже заполнен", text)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            "survey:overwrite:2026-08-14",
        )

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    async def test_stale_overwrite_button_cannot_change_another_day(self, _today) -> None:
        callback = FakeCallback("survey:overwrite:2026-08-13")
        state = FakeState()

        await cb_overwrite(callback, state)

        self.assertIsNone(state.state)
        callback.answer.assert_awaited_once_with(
            "Эта кнопка устарела. Откройте /report снова.",
            show_alert=True,
        )

    @patch("handlers.daily.today_msk", return_value=date(2026, 8, 14))
    async def test_overwrite_button_clears_previous_flow_data(self, _today) -> None:
        callback = FakeCallback("survey:overwrite:2026-08-14")
        state = FakeState()
        state.state = DailyForm.debt_paid
        state.data = {"edit_mode": True, "income_card": 999}

        await cb_overwrite(callback, state)

        self.assertEqual(state.state, DailyForm.income_card)
        self.assertEqual(state.data, {"report_date": "2026-08-14"})
        callback.answer.assert_awaited_once_with()
