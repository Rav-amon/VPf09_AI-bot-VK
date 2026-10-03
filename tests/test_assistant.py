"""Проверки памяти, диалогов, контекста и клавиатур без сети."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from keyboards.builder import render_keyboard
from models.commands import Cmd, Screen
from models.records import (
    MAX_HISTORY_MESSAGES,
    ChatMessage,
    ContextMessage,
    create_user_record,
    record_from_dict,
    record_to_dict,
)
from models.screen import ScreenResponse
from services.ai_service import AIService
from services.assistant import AssistantApp
from services.chat_service import ChatService
from services.dialog_service import MAX_DIALOGS, DialogService
from services.memory_service import MemoryService
from services.providers.gemini import build_gemini_contents
from storage.json_user_storage import JsonUserStorage
from utils.context import normalize_turns
from utils.errors import ServiceError
from utils.text import split_vk_text, validate_user_text


class FakeProvider:
    """Провайдер без сети: запоминает последний запрос и возвращает заданный текст."""

    name = "fake"
    model = "fake-model"

    def __init__(self, reply: str = "Готово", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.history_length = 0
        self.user_message = ""
        self.system_prompt = ""

    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[ContextMessage],
        user_message: str,
    ) -> str:
        self.system_prompt = system_prompt
        self.history_length = len(history)
        self.user_message = user_message
        if self.fail:
            raise ServiceError("api_unavailable", "Модель временно недоступна.")
        return self.reply


class MemoryTests(unittest.TestCase):
    def test_trim_drops_oldest_messages(self) -> None:
        memory = MemoryService(max_messages=MAX_HISTORY_MESSAGES)
        messages = [
            ChatMessage(role="user", content=str(index), timestamp="t")
            for index in range(MAX_HISTORY_MESSAGES + 5)
        ]
        trimmed = memory.trim(messages)
        self.assertEqual(len(trimmed), MAX_HISTORY_MESSAGES)
        self.assertEqual(trimmed[0].content, "5")
        self.assertEqual(trimmed[-1].content, str(MAX_HISTORY_MESSAGES + 4))

    def test_context_starts_with_user_and_merges_roles(self) -> None:
        turns = normalize_turns(
            [
                ContextMessage(role="assistant", content="лишнее"),
                ContextMessage(role="user", content="первый"),
                ContextMessage(role="user", content="второй"),
                ContextMessage(role="assistant", content="ответ"),
            ]
        )
        self.assertEqual([item.role for item in turns], ["user", "assistant"])
        self.assertEqual(turns[0].content, "первый\nвторой")


class TextTests(unittest.TestCase):
    def test_empty_message_is_rejected(self) -> None:
        self.assertIsNotNone(validate_user_text("   "))

    def test_long_answer_is_split_on_words(self) -> None:
        chunks = split_vk_text("слово " * 2000, limit=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))


class StorageAndDialogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.storage = JsonUserStorage(Path(self._directory.name))
        self.memory = MemoryService()
        self.dialogs = DialogService(self.storage, self.memory)

    async def asyncTearDown(self) -> None:
        self._directory.cleanup()

    async def test_roundtrip_and_dialog_switch(self) -> None:
        created = await self.dialogs.create_dialog(7)
        second = created.dialogs[-1]
        renamed = await self.dialogs.rename_dialog(7, second.id, "Рабочий вопрос")
        self.assertEqual(renamed.active_dialog_id, second.id)
        loaded = await self.storage.get(7)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.dialogs[-1].title, "Рабочий вопрос")
        raw = json.loads((Path(self._directory.name) / "7.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["user_id"], 7)
        self.assertIn("messages", raw["dialogs"][0])

    async def test_delete_last_dialog_creates_default(self) -> None:
        record = await self.dialogs.ensure_user(3)
        _updated, note = await self.dialogs.delete_dialog(3, record.dialogs[0].id)
        self.assertIn("Основной", note)
        fresh = await self.storage.get(3)
        assert fresh is not None
        self.assertEqual(len(fresh.dialogs), 1)
        self.assertEqual(fresh.dialogs[0].title, "Основной")

    async def test_role_changes_only_active_dialog(self) -> None:
        await self.dialogs.ensure_user(4)
        created = await self.dialogs.create_dialog(4)
        first_id = created.dialogs[0].id
        await self.dialogs.set_role(4, "programmer")
        record = await self.storage.get(4)
        assert record is not None
        roles = {dialog.id: dialog.role for dialog in record.dialogs}
        self.assertEqual(roles[first_id], "assistant")
        self.assertEqual(roles[record.active_dialog_id], "programmer")

    async def test_dialog_limit(self) -> None:
        await self.dialogs.ensure_user(5)
        for _ in range(MAX_DIALOGS - 1):
            await self.dialogs.create_dialog(5)
        with self.assertRaises(ServiceError) as caught:
            await self.dialogs.create_dialog(5)
        self.assertEqual(caught.exception.code, "dialog_limit")

    async def test_corrupt_file_is_not_overwritten(self) -> None:
        path = Path(self._directory.name) / "9.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(ServiceError) as caught:
            await self.storage.get(9)
        self.assertEqual(caught.exception.code, "storage_corrupt")
        self.assertEqual(path.read_text(encoding="utf-8"), "{")


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        storage = JsonUserStorage(Path(self._directory.name))
        self.memory = MemoryService()
        self.dialogs = DialogService(storage, self.memory)
        self.provider = FakeProvider(reply="Ответ помощника")
        self.chat = ChatService(self.dialogs, self.memory, AIService(self.provider))
        self.app = AssistantApp(self.dialogs, self.chat, AIService(self.provider))

    async def asyncTearDown(self) -> None:
        self._directory.cleanup()

    async def test_answer_saves_pair_and_passes_history(self) -> None:
        await self.dialogs.ensure_user(11)
        first = await self.chat.answer(11, "Привет")
        self.chat._last_call.clear()
        second = await self.chat.answer(11, "Как дела?")
        self.assertEqual(first, "Ответ помощника")
        self.assertEqual(second, "Ответ помощника")
        self.assertEqual(self.provider.history_length, 2)
        record = await self.dialogs.get_record(11)
        self.assertEqual(len(record.dialogs[0].messages), 4)

    async def test_failed_model_does_not_save_messages(self) -> None:
        self.provider.fail = True
        with self.assertRaises(ServiceError):
            await self.chat.answer(12, "Вопрос")
        record = await self.dialogs.get_record(12)
        self.assertEqual(record.dialogs[0].messages, [])

    async def test_screen_lists_dialogs(self) -> None:
        await self.app.create_dialog(15)
        screen = await self.app.open_dialogs(15, 0)
        self.assertEqual(screen.screen, Screen.DIALOGS)
        self.assertGreaterEqual(len(screen.dialogs), 2)
        keyboard = json.loads(render_keyboard(screen))
        self.assertTrue(keyboard["inline"])
        labels = [
            button["action"]["label"]
            for row in keyboard["buttons"]
            for button in row
        ]
        self.assertIn("Удалить", labels)


class GeminiContentTests(unittest.TestCase):
    def test_assistant_role_becomes_model(self) -> None:
        contents = build_gemini_contents(
            [
                ContextMessage(role="user", content="привет"),
                ContextMessage(role="assistant", content="здравствуйте"),
            ],
            "как дела?",
        )
        self.assertEqual([item.role for item in contents], ["user", "model", "user"])
        self.assertEqual(contents[1].parts[0].text, "здравствуйте")

    def test_record_schema_keeps_message_fields(self) -> None:
        record = create_user_record(1)
        record.dialogs[0].messages.append(ChatMessage("user", "текст", "2026-01-01T00:00:00Z"))
        restored = record_from_dict(record_to_dict(record), 1)
        message = restored.dialogs[0].messages[0]
        self.assertEqual(message.role, "user")
        self.assertEqual(message.content, "текст")
        self.assertEqual(message.timestamp, "2026-01-01T00:00:00Z")


class KeyboardTests(unittest.TestCase):
    def test_main_menu_has_russian_actions(self) -> None:
        keyboard = json.loads(
            render_keyboard(ScreenResponse(text="", screen=Screen.MAIN, role_id="assistant")),
        )
        self.assertTrue(keyboard["inline"])
        labels = [
            button["action"]["label"]
            for row in keyboard["buttons"]
            for button in row
        ]
        colors = [
            button["color"]
            for row in keyboard["buttons"]
            for button in row
        ]
        self.assertEqual(
            labels,
            [
                "Новый диалог",
                "Список диалогов",
                "Настройки",
                "Помощь",
                "✓ Обычный помощник",
                "Программист",
                "Преподаватель",
                "Бизнес-консультант",
                "Дружелюбный собеседник",
            ],
        )
        self.assertTrue(all(colors))
        self.assertLessEqual(len(keyboard["buttons"]), 6)
        commands = []
        for row in keyboard["buttons"]:
            for button in row:
                payload = button["action"]["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                commands.append(payload["cmd"])
        self.assertIn(Cmd.NEW_DIALOG, commands)
        self.assertIn(Cmd.SET_ROLE, commands)


if __name__ == "__main__":
    unittest.main()
