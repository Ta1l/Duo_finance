"""Клавиатуры."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

SKIP_BUTTON_TEXT = "Пропустить (0)"
SKIP_SYNONYMS = {"пропустить (0)", "пропустить", "skip"}


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


def is_skip_text(text: str | None) -> bool:
    return bool(text) and text.strip().lower() in SKIP_SYNONYMS
