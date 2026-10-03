"""Диалоги пользователя: создание, переключение, роли и история."""

from __future__ import annotations

import re
from typing import TypeVar

from models.records import (
    DEFAULT_DIALOG_TITLE,
    DEFAULT_ROLE_ID,
    ChatMessage,
    Dialog,
    UserRecord,
    active_dialog,
    create_dialog,
    utc_now,
)
from models.roles import get_role
from services.memory_service import MemoryService
from storage.json_user_storage import JsonUserStorage, Mutator
from utils.errors import ServiceError

T = TypeVar("T")

MAX_DIALOGS = 10
MAX_TITLE_LENGTH = 80
DIALOG_ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")


def normalize_title(raw: str) -> str:
    """Сжимает пробелы и отклоняет пустое или слишком длинное название."""
    title = " ".join(raw.split())
    if not title:
        raise ServiceError("invalid_title", "Название не может быть пустым.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ServiceError(
            "invalid_title",
            f"Название длиннее {MAX_TITLE_LENGTH} символов. Сократите его.",
        )
    return title


def is_dialog_id(value: str) -> bool:
    """Проверяет формат идентификатора, который бот сам кладёт в кнопки."""
    return bool(DIALOG_ID_PATTERN.fullmatch(value))


class DialogService:
    """Менеджер диалогов поверх JSON-хранилища."""

    def __init__(self, storage: JsonUserStorage, memory: MemoryService) -> None:
        self._storage = storage
        self._memory = memory

    async def update(self, user_id: int, mutator: Mutator[T]) -> T:
        """Прокси к хранилищу: нужен, чтобы чат сохранял обмен под той же блокировкой."""
        return await self._storage.update(user_id, mutator)

    async def ensure_user(self, user_id: int) -> UserRecord:
        """Гарантирует, что у пользователя есть файл и активный диалог."""
        return await self._storage.ensure(user_id)

    async def get_record(self, user_id: int) -> UserRecord:
        """Возвращает карточку. Создаёт её, если пользователь пишет впервые."""
        return await self.ensure_user(user_id)

    def find_dialog(self, record: UserRecord, dialog_id: str) -> Dialog:
        """Ищет диалог внутри уже загруженной карточки."""
        if not is_dialog_id(dialog_id):
            raise ServiceError("dialog_not_found", "Такого диалога нет.")
        for dialog in record.dialogs:
            if dialog.id == dialog_id:
                return dialog
        raise ServiceError("dialog_not_found", "Такого диалога нет.")

    async def create_dialog(self, user_id: int) -> UserRecord:
        """Добавляет пустой диалог и делает его активным."""
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> UserRecord:
            if len(record.dialogs) >= MAX_DIALOGS:
                raise ServiceError(
                    "dialog_limit",
                    f"Можно держать не больше {MAX_DIALOGS} диалогов. Удалите один из списка.",
                )
            # Новый диалог начинает с обычного помощника, режим не копируется.
            dialog = create_dialog(f"Диалог {len(record.dialogs) + 1}", DEFAULT_ROLE_ID)
            record.dialogs.append(dialog)
            record.active_dialog_id = dialog.id
            return record

        return await self._storage.update(user_id, mutate)

    async def switch_dialog(self, user_id: int, dialog_id: str) -> UserRecord:
        """Меняет активный контекст: историю и system prompt этого диалога."""
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> UserRecord:
            dialog = self.find_dialog(record, dialog_id)
            record.active_dialog_id = dialog.id
            dialog.updated_at = utc_now()
            return record

        return await self._storage.update(user_id, mutate)

    async def rename_dialog(self, user_id: int, dialog_id: str, title: str) -> UserRecord:
        """Переименовывает один диалог, не трогая остальные."""
        clean_title = normalize_title(title)
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> UserRecord:
            dialog = self.find_dialog(record, dialog_id)
            dialog.title = clean_title
            dialog.updated_at = utc_now()
            return record

        return await self._storage.update(user_id, mutate)

    async def delete_dialog(self, user_id: int, dialog_id: str) -> tuple[UserRecord, str]:
        """Удаляет диалог. Если он был последним, создаёт новый «Основной»."""
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> tuple[UserRecord, str]:
            dialog = self.find_dialog(record, dialog_id)
            title = dialog.title
            record.dialogs = [item for item in record.dialogs if item.id != dialog.id]
            if not record.dialogs:
                fresh = create_dialog(DEFAULT_DIALOG_TITLE)
                record.dialogs.append(fresh)
                record.active_dialog_id = fresh.id
                note = (
                    f"Диалог «{title}» удалён. "
                    "Это был последний диалог, поэтому создан новый «Основной»."
                )
                return record, note
            if record.active_dialog_id == dialog.id:
                record.active_dialog_id = record.dialogs[-1].id
            note = f"Диалог «{title}» удалён."
            return record, note

        return await self._storage.update(user_id, mutate)

    async def set_role(self, user_id: int, role_id: str) -> UserRecord:
        """Меняет режим только у активного диалога."""
        role = get_role(role_id)
        if role.id != role_id:
            raise ServiceError("invalid_role", "Такого режима нет. Выберите кнопку из списка.")
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> UserRecord:
            dialog = active_dialog(record)
            dialog.role = role.id
            dialog.updated_at = utc_now()
            return record

        return await self._storage.update(user_id, mutate)

    async def clear_history(self, user_id: int, dialog_id: str = "") -> UserRecord:
        """Очищает сообщения выбранного диалога. Название и режим остаются."""
        await self.ensure_user(user_id)

        def mutate(record: UserRecord) -> UserRecord:
            if dialog_id:
                dialog = self.find_dialog(record, dialog_id)
            else:
                dialog = active_dialog(record)
            dialog.messages = []
            dialog.updated_at = utc_now()
            return record

        return await self._storage.update(user_id, mutate)

    async def remember_exchange(
        self,
        record: UserRecord,
        user_text: str,
        assistant_text: str,
    ) -> None:
        """Добавляет пару реплик в активный диалог и обрезает историю до лимита."""
        dialog = active_dialog(record)
        now = utc_now()
        dialog.messages = self._memory.trim(
            [
                *dialog.messages,
                ChatMessage(role="user", content=user_text, timestamp=now),
                ChatMessage(role="assistant", content=assistant_text, timestamp=now),
            ]
        )
        dialog.updated_at = now
