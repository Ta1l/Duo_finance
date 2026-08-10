"""ORM-модели (SQLAlchemy 2.x, async)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Игрок пары (всего два слота: 'A' и 'B')."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    slot: Mapped[str] = mapped_column(String(1))  # 'A' | 'B'

    debt_start: Mapped[float] = mapped_column(Float, default=0.0)
    debt_current: Mapped[float] = mapped_column(Float, default=0.0)
    streak_days: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    reports: Mapped[list["DailyReport"]] = relationship(
        back_populates="user", lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.first_name or self.username or f"Игрок {self.slot}"


class DailyReport(Base):
    """Ежедневный отчёт. Один отчёт на (user_id, report_date)."""

    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "report_date", name="uq_report_user_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    report_date: Mapped[date] = mapped_column(Date, index=True)

    income_card: Mapped[float] = mapped_column(Float, default=0.0)
    expenses: Mapped[float] = mapped_column(Float, default=0.0)
    in_transit_earned: Mapped[float] = mapped_column(Float, default=0.0)
    debt_paid: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="reports")


class MetaKV(Base):
    """
    Служебные ключи для идемпотентности фоновых рассылок:
    - payout:<ISO-неделя>            — выплата «в пути» уже разослана
    - weekly_report:<ISO-неделя>     — воскресный отчёт уже сгенерирован
    """

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")
