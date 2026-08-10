"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class DailyForm(StatesGroup):
    """Ежедневный опрос за день (4 шага по ТЗ)."""

    income_card = State()        # Шаг 1: приход на карту
    expenses = State()           # Шаг 2: расходы
    in_transit_earned = State()  # Шаг 3: заработано «в пути»
    debt_paid = State()          # Шаг 4: внесено в долг (или «Пропустить (0)»)
