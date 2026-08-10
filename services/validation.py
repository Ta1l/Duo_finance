"""Парсинг и валидация пользовательского ввода."""
from __future__ import annotations

import math

MAX_AMOUNT = 100_000_000.0  # верхняя граница от опечаток


def parse_amount(text: str | None) -> float | None:
    """
    Парсит денежную сумму из текста: '1500', '2450.50', '1 234,56', ' 0 '.

    Возвращает None, если значение невалидно:
    не число / отрицательное / бесконечность / за пределом MAX_AMOUNT.
    """
    if text is None:
        return None
    cleaned = text.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0 or value > MAX_AMOUNT:
        return None
    return round(value, 2)
