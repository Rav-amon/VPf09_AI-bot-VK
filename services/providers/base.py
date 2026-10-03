"""Контракт провайдера модели. Новый провайдер реализует тот же метод complete."""

from __future__ import annotations

from typing import Protocol

from models.records import ContextMessage


class AIProvider(Protocol):
    """Поставщик ответов. Слой VK и диалоги про этот класс не знают."""

    name: str
    model: str

    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[ContextMessage],
        user_message: str,
    ) -> str:
        """Возвращает текст ответа модели."""
