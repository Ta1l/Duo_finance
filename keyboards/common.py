"""Клавиатуры."""
from datetime import date

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from services.dates import report_day_number

SKIP_BUTTON_TEXT = "Пропустить (0)"
SKIP_SYNONYMS = {"пропустить (0)", "пропустить", "skip"}
WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def skip_keyboard() -> ReplyKeyboardMarkup:
    """Reply-кнопка «Пропустить (0)» для 4-го шага опроса."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SKIP_BUTTON_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


def overwrite_keyboard() -> InlineKeyboardMarkup:
    """Inline-подтверждение перезаписи уже заполненного отчёта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Заполнить заново", callback_data="survey:overwrite"
                ),
                InlineKeyboardButton(text="❌ Оставить", callback_data="survey:dismiss"),
            ]
        ]
    )


def edit_day_keyboard(
    days: list[date], filled_days: set[date]
) -> InlineKeyboardMarkup:
    """Список доступных дней текущей недели для создания или перезаписи."""
    rows = []
    for day in days:
        marker = "✅" if day in filled_days else "➕"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{marker} День {report_day_number(day)} · "
                        f"{WEEKDAY_SHORT[day.weekday()]} {day:%d.%m}"
                    ),
                    callback_data=f"editday:{day.isoformat()}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_skip_text(text: str | None) -> bool:
    return bool(text) and text.strip().lower() in SKIP_SYNONYMS
