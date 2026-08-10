"""Пакет services.

Важно: __init__ намеренно пуст (без eager-импортов), чтобы «чистые» модули
(calculations, dates, validation) можно было импортировать и тестировать
без установки aiogram/SQLAlchemy.
"""
