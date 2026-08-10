"""Тесты разбора даты и превью отчёта для /editday."""
import sys
import types
import asyncio
from datetime import date

# Заглушки для aiogram, чтобы тесты можно было запускать без установки пакета.
aiogram = types.ModuleType("aiogram")
aiogram.Bot = type("Bot", (), {})

class FProxy:
    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def func(self, *args, **kwargs):
        return self

    def __eq__(self, other):
        return True

    def __iter__(self):
        yield from ()

aiogram.F = FProxy()

class Router:
    def __init__(self, *args, **kwargs):
        pass

    def message(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def callback_query(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

aiogram.Router = Router

filters = types.ModuleType("aiogram.filters")

class Command:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return self

filters.Command = Command
sys.modules["aiogram.filters"] = filters

fsm = types.ModuleType("aiogram.fsm")
sys.modules["aiogram.fsm"] = fsm

fsm_context = types.ModuleType("aiogram.fsm.context")
fsm_context.FSMContext = type("FSMContext", (), {})
sys.modules["aiogram.fsm.context"] = fsm_context

fsm_state = types.ModuleType("aiogram.fsm.state")
fsm_state.State = type("State", (), {})
fsm_state.StatesGroup = type("StatesGroup", (), {})
sys.modules["aiogram.fsm.state"] = fsm_state

fsm_storage = types.ModuleType("aiogram.fsm.storage")
sys.modules["aiogram.fsm.storage"] = fsm_storage

storage_base = types.ModuleType("aiogram.fsm.storage.base")
storage_base.BaseStorage = type("BaseStorage", (), {})
storage_base.StorageKey = type("StorageKey", (), {})
sys.modules["aiogram.fsm.storage.base"] = storage_base

memory_storage = types.ModuleType("aiogram.fsm.storage.memory")
memory_storage.MemoryStorage = type("MemoryStorage", (), {})
sys.modules["aiogram.fsm.storage.memory"] = memory_storage

aiogram.types = types.ModuleType("aiogram.types")
aiogram.types.CallbackQuery = type("CallbackQuery", (), {})
aiogram.types.Message = type("Message", (), {})
aiogram.types.ReplyKeyboardRemove = type("ReplyKeyboardRemove", (), {})
aiogram.types.InlineKeyboardButton = type("InlineKeyboardButton", (), {})
aiogram.types.InlineKeyboardMarkup = type("InlineKeyboardMarkup", (), {})
aiogram.types.KeyboardButton = type("KeyboardButton", (), {})
aiogram.types.ReplyKeyboardMarkup = type("ReplyKeyboardMarkup", (), {})
sys.modules["aiogram.types"] = aiogram.types

client = types.ModuleType("aiogram.client")
sys.modules["aiogram.client"] = client

client_default = types.ModuleType("aiogram.client.default")
client_default.DefaultBotProperties = type("DefaultBotProperties", (), {})
sys.modules["aiogram.client.default"] = client_default

aiogram.client = client
sys.modules["aiogram.client.default"] = client_default

aiogram.enums = types.ModuleType("aiogram.enums")
aiogram.enums.ParseMode = type("ParseMode", (), {})
sys.modules["aiogram.enums"] = aiogram.enums

sys.modules["aiogram"] = aiogram
sys.modules["aiogram.client"] = client
sys.modules["aiogram.enums"] = aiogram.enums

from handlers.daily import _format_report_preview, cmd_edit_day, DailyForm, Q_EDITDAY_DATE
from services.dates import parse_date


class DummyReport:
    def __init__(self, income_card: float, expenses: float, in_transit_earned: float, debt_paid: float) -> None:
        self.income_card = income_card
        self.expenses = expenses
        self.in_transit_earned = in_transit_earned
        self.debt_paid = debt_paid


class FakeState:
    def __init__(self):
        self._state = None

    async def get_state(self):
        return self._state

    async def clear(self):
        self._state = None

    async def set_state(self, state):
        self._state = state

    async def update_data(self, **kwargs):
        self.data = kwargs


class FakeMessage:
    def __init__(self):
        self.text = ""
        self.answer_text = None

    async def answer(self, text):
        self.answer_text = text


def test_parse_date_valid() -> None:
    assert parse_date("04.06.2026") == date(2026, 6, 4)


def test_parse_date_invalid() -> None:
    assert parse_date("2026-06-04") is None
    assert parse_date("32.01.2026") is None
    assert parse_date("") is None


def test_format_report_preview_for_missing_report() -> None:
    assert _format_report_preview(date(2026, 6, 4), None) == (
        "За 04.06.2026 данных нет. Начнём новый отчёт за этот день."
    )


def test_format_report_preview_for_existing_report() -> None:
    report = DummyReport(1000.0, 500.0, 250.0, 100.0)
    assert _format_report_preview(date(2026, 6, 4), report) == (
        "За 04.06.2026 уже есть данные:\n"
        "💵 Приход: 1 000 ₽ · 🧾 Расходы: 500 ₽\n"
        "🛣 В пути: 250 ₽ · 💳 В долг: 100 ₽"
    )


def test_cmd_edit_day_sets_state_and_asks_for_date() -> None:
    state = FakeState()
    message = FakeMessage()

    asyncio.run(cmd_edit_day(message, state, session=None, db_user=None))  # type: ignore[arg-type]

    assert message.answer_text == Q_EDITDAY_DATE
    assert asyncio.run(state.get_state()) == DailyForm.date_selection
