"""Выбор провайдера модели. Сейчас подключён только Gemini через ProxyAPI."""

from __future__ import annotations

from config.settings import Settings
from services.providers.base import AIProvider
from services.providers.gemini import GeminiProvider
from utils.errors import ServiceError


def create_provider(settings: Settings) -> AIProvider:
    """Создаёт провайдера по имени. Новая модель добавляется новой веткой."""
    if settings.ai_provider == "gemini":
        return GeminiProvider(
            api_key=settings.proxy_api_key,
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            timeout_ms=settings.request_timeout_ms,
        )
    raise ServiceError(
        "config_error",
        f"Провайдер «{settings.ai_provider}» пока не подключён.",
    )
