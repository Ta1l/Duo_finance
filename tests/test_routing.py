from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest import IsolatedAsyncioTestCase

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User

from bot import build_dispatcher
from config import Config
from database import crud
from database.engine import init_models, make_engine, make_session_factory


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers=None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:  # pragma: no cover - async generator required by BaseSession
            yield b""


class CommandRoutingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.config = Config(
            bot_token="123456:TEST",
            database_url="sqlite+aiosqlite:///:memory:",
            start_debt=10_000,
            eta_window_days=14,
            survey_hour=23,
            survey_minute=30,
            payout_hour=12,
            proxy_url=None,
        )
        self.engine = make_engine(self.config.database_url)
        await init_models(self.engine)
        self.pool = make_session_factory(self.engine)
        async with self.pool() as session:
            await crud.create_user(
                session,
                tg_id=101,
                username="tester",
                first_name="Tester",
                slot="A",
                start_debt=self.config.start_debt,
            )
            await session.commit()

        self.api = RecordingSession()
        self.bot = Bot(self.config.bot_token, session=self.api)
        self.dispatcher = build_dispatcher(
            session_pool=self.pool,
            config=self.config,
        )
        self.user = User(id=101, is_bot=False, first_name="Tester")
        self.chat = Chat(id=101, type="private")
        self.update_id = 0

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.engine.dispose()

    async def send_command(self, command: str, user: User | None = None) -> None:
        self.update_id += 1
        sender = user or self.user
        message = Message(
            message_id=self.update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=sender.id, type="private"),
            from_user=sender,
            text=command,
            entities=[MessageEntity(type="bot_command", offset=0, length=len(command))],
        )
        await self.dispatcher.feed_update(
            self.bot,
            Update(update_id=self.update_id, message=message),
        )

    async def test_report_and_editday_are_not_caught_by_fallback(self) -> None:
        await self.send_command("/report")
        report_response = self.api.methods[-1]
        self.assertIn("Шаг 1/4", report_response.text)

        await self.send_command("/editday")
        edit_response = self.api.methods[-1]
        self.assertIn("Выберите день текущей недели", edit_response.text)
        self.assertEqual(len(edit_response.reply_markup.inline_keyboard), 5)

        self.update_id += 1
        menu_message = Message(
            message_id=self.update_id,
            date=datetime.now(timezone.utc),
            chat=self.chat,
            from_user=self.user,
            text=edit_response.text,
            reply_markup=edit_response.reply_markup,
        )
        callback = CallbackQuery(
            id="editday-callback",
            from_user=self.user,
            chat_instance="test-chat",
            message=menu_message,
            data="editday:2026-08-10",
        )
        await self.dispatcher.feed_update(
            self.bot,
            Update(update_id=self.update_id, callback_query=callback),
        )
        self.assertIn("Шаг 1/4", self.api.methods[-1].text)

        await self.send_command("/help")
        help_response = self.api.methods[-1]
        self.assertIn("23:30", help_response.text)
        self.assertIn("12:00", help_response.text)

        outsider = User(id=202, is_bot=False, first_name="Outsider")
        await self.send_command("/startfoo", user=outsider)
        access_response = self.api.methods[-1]
        self.assertIn("приватный бот", access_response.text)
