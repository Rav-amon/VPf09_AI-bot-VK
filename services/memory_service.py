"""Краткосрочная память: окно из последних сообщений и контекст для модели."""

from __future__ import annotations

from models.records import MAX_HISTORY_MESSAGES, ChatMessage, ContextMessage
from utils.context import normalize_turns


class MemoryService:
    """Обрезает историю и готовит реплики без системных сообщений."""

    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES) -> None:
        if max_messages < 1:
            raise ValueError("Размер памяти должен быть больше нуля")
        self._max_messages = max_messages

    @property
    def max_messages(self) -> int:
        """Сколько последних сообщений хранится в одном диалоге."""
        return self._max_messages

    def trim(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Оставляет только хвост истории. Старые сообщения отбрасываются."""
        if len(messages) <= self._max_messages:
            return list(messages)
        return list(messages[-self._max_messages :])

    def build_context(self, messages: list[ChatMessage]) -> list[ContextMessage]:
        """Берёт последние сообщения диалога и нормализует роли для запроса."""
        window = self.trim(messages)
        turns = [
            ContextMessage(role=item.role, content=item.content)
            for item in window
            if item.role in {"user", "assistant"}
        ]
        return normalize_turns(turns)
