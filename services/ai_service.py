"""Сервис модели: проверяет запрос и прячет детали провайдера."""

from __future__ import annotations

import logging

from models.records import ContextMessage
from services.providers.base import AIProvider
from utils.errors import ServiceError

logger = logging.getLogger(__name__)


class AIService:
    """Единая точка вызова модели для остального приложения."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    @property
    def model_name(self) -> str:
        """Имя модели для экрана настроек."""
        return self._provider.model

    @property
    def provider_name(self) -> str:
        """Имя провайдера, чтобы позже показать другую подключённую модель."""
        return self._provider.name

    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[ContextMessage],
        user_message: str,
    ) -> str:
        """Передаёт system prompt, историю и новое сообщение. Пустой текст не уходит в API."""
        cleaned = user_message.strip()
        if not cleaned:
            raise ServiceError(
                "empty_message",
                "Пустое сообщение не отправляется. Напишите вопрос текстом.",
            )
        if not system_prompt.strip():
            raise ServiceError("config_error", "Для диалога не задан режим общения.")
        try:
            text = await self._provider.complete(
                system_prompt=system_prompt,
                history=history,
                user_message=cleaned,
            )
        except ServiceError:
            raise
        except Exception as exc:
            logger.warning(
                "Необработанная ошибка AI-провайдера",
                extra={"context": {"error_type": type(exc).__name__, "model": self.model_name}},
            )
            raise ServiceError(
                "api_unavailable",
                "Не получилось получить ответ от модели. Попробуйте ещё раз чуть позже.",
                {"error_type": type(exc).__name__},
            ) from exc
        if not text.strip():
            raise ServiceError(
                "empty_response",
                "Модель не вернула текст. Переформулируйте вопрос и отправьте его снова.",
            )
        return text.strip()
