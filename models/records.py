"""Записи пользователя, диалога и сообщения. Хранятся в JSON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_hex
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_DIALOG_TITLE = "Основной"
DEFAULT_ROLE_ID = "assistant"
DIALOG_ID_LENGTH = 12
MAX_HISTORY_MESSAGES = 100


def utc_now() -> str:
    """Время события в UTC, чтобы файлы не зависели от часового пояса сервера."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_dialog_id() -> str:
    """Короткий идентификатор: в payload кнопки VK помещается не больше 255 байт."""
    return token_hex(DIALOG_ID_LENGTH // 2)


@dataclass(slots=True)
class ChatMessage:
    """Одно сообщение краткосрочной памяти."""

    role: str
    content: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """Реплика, которая уходит в модель. Время хранения здесь не нужно."""

    role: str
    content: str


@dataclass(slots=True)
class Dialog:
    """Независимый диалог со своим режимом и историей."""

    id: str
    title: str
    role: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage]


@dataclass(slots=True)
class UserSettings:
    """Настройки пользователя. Сейчас язык интерфейса всегда русский."""

    language: str = "ru"


@dataclass(slots=True)
class UserRecord:
    """Полное состояние одного пользователя ВКонтакте."""

    user_id: int
    active_dialog_id: str
    settings: UserSettings
    dialogs: list[Dialog]
    schema_version: int = SCHEMA_VERSION


def create_dialog(title: str, role: str = DEFAULT_ROLE_ID) -> Dialog:
    """Создаёт пустой диалог с новым идентификатором."""
    now = utc_now()
    return Dialog(
        id=new_dialog_id(),
        title=title,
        role=role,
        created_at=now,
        updated_at=now,
        messages=[],
    )


def create_user_record(user_id: int) -> UserRecord:
    """Первый вход: один диалог «Основной» и режим обычного помощника."""
    dialog = create_dialog(DEFAULT_DIALOG_TITLE)
    return UserRecord(
        user_id=user_id,
        active_dialog_id=dialog.id,
        settings=UserSettings(),
        dialogs=[dialog],
    )


def active_dialog(record: UserRecord) -> Dialog:
    """Возвращает активный диалог и чинит ссылку, если она потерялась."""
    for dialog in record.dialogs:
        if dialog.id == record.active_dialog_id:
            return dialog
    if not record.dialogs:
        dialog = create_dialog(DEFAULT_DIALOG_TITLE)
        record.dialogs.append(dialog)
    record.active_dialog_id = record.dialogs[0].id
    return record.dialogs[0]


def message_from_dict(raw: dict[str, Any]) -> ChatMessage:
    """Собирает сообщение из JSON. Пустые поля заменяются безопасными значениями."""
    role = str(raw.get("role", "user"))
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return ChatMessage(
        role=role,
        content=str(raw.get("content", "")),
        timestamp=str(raw.get("timestamp", "")),
    )


def dialog_from_dict(raw: dict[str, Any]) -> Dialog:
    """Собирает диалог из JSON."""
    messages_raw = raw.get("messages", [])
    messages = [
        message_from_dict(item)
        for item in messages_raw
        if isinstance(item, dict)
    ]
    return Dialog(
        id=str(raw.get("id", new_dialog_id())),
        title=str(raw.get("title", DEFAULT_DIALOG_TITLE)),
        role=str(raw.get("role", DEFAULT_ROLE_ID)),
        created_at=str(raw.get("created_at", utc_now())),
        updated_at=str(raw.get("updated_at", utc_now())),
        messages=messages,
    )


def record_from_dict(raw: dict[str, Any], user_id: int) -> UserRecord:
    """Собирает карточку пользователя. Идентификатор берётся из имени файла."""
    dialogs_raw = raw.get("dialogs", [])
    dialogs = [
        dialog_from_dict(item)
        for item in dialogs_raw
        if isinstance(item, dict)
    ]
    settings_raw = raw.get("settings", {})
    language = "ru"
    if isinstance(settings_raw, dict):
        language = str(settings_raw.get("language", "ru"))
    record = UserRecord(
        user_id=user_id,
        active_dialog_id=str(raw.get("active_dialog_id", "")),
        settings=UserSettings(language=language or "ru"),
        dialogs=dialogs,
        schema_version=SCHEMA_VERSION,
    )
    # Активный диалог и пустой список восстанавливаются сразу при чтении.
    active_dialog(record)
    for dialog in record.dialogs:
        if len(dialog.messages) > MAX_HISTORY_MESSAGES:
            dialog.messages = dialog.messages[-MAX_HISTORY_MESSAGES:]
    return record


def record_to_dict(record: UserRecord) -> dict[str, Any]:
    """Готовит карточку к записи в JSON."""
    return {
        "schema_version": SCHEMA_VERSION,
        "user_id": record.user_id,
        "active_dialog_id": record.active_dialog_id,
        "settings": {"language": record.settings.language},
        "dialogs": [
            {
                "id": dialog.id,
                "title": dialog.title,
                "role": dialog.role,
                "created_at": dialog.created_at,
                "updated_at": dialog.updated_at,
                "messages": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "timestamp": message.timestamp,
                    }
                    for message in dialog.messages
                ],
            }
            for dialog in record.dialogs
        ],
    }
