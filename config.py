"""Конфигурация приложения из переменных окружения / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    start_debt: float
    eta_window_days: int      # окно N дней для avg_daily_debt_paid (14 или 30 по ТЗ)
    survey_hour: int          # ежедневный опрос (по умолчанию 23:30 МСК)
    survey_minute: int
    payout_hour: int          # уведомление о выплате «в пути» по четвергам
    proxy_url: str | None     # SOCKS5 прокси для России: socks5://user:pass@host:port


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Создайте .env по образцу .env.example "
            "или экспортируйте переменную окружения."
        )

    return Config(
        bot_token=token,
        database_url=os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./duo_finance.db"
        ),
        start_debt=float(os.getenv("START_DEBT", "300000")),
        eta_window_days=int(os.getenv("ETA_WINDOW_DAYS", "14")),
        survey_hour=int(os.getenv("SURVEY_HOUR", "23")),
        survey_minute=int(os.getenv("SURVEY_MINUTE", "30")),
        payout_hour=int(os.getenv("PAYOUT_HOUR", "9")),
        proxy_url=os.getenv("PROXY_URL", "").strip() or None,
    )
