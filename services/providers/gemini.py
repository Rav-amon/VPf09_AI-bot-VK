"""Gemini через Google GenAI SDK и базовый адрес ProxyAPI."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from models.records import ContextMessage
from utils.context import normalize_turns
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "Не получилось получить ответ от модели. "
    "Проверьте соединение и попробуйте ещё раз чуть позже."
)
EMPTY_RESPONSE_MESSAGE = "Модель не вернула текст. Переформулируйте вопрос и отправьте его снова."
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def build_gemini_contents(history: list[ContextMessage], user_message: str) -> list[types.Content]:
    """Собирает contents: прошлая история и новое сообщение пользователя."""
    turns = normalize_turns([*history, ContextMessage(role="user", content=user_message)])
    contents: list[types.Content] = []
    for item in turns:
        role = "model" if item.role == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=item.content)]))
    return contents


def is_transient(exc: Exception) -> bool:
    """Сетевые и временные ошибки API можно повторить. Текст исключения не логируем."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError):
        return exc.code in TRANSIENT_STATUS_CODES
    return isinstance(exc, (TimeoutError, ConnectionError))


class GeminiProvider:
    """Клиент Gemini. Модель и адрес задаются снаружи, чтобы их было легко сменить."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        temperature: float,
        max_output_tokens: int,
        timeout_ms: int,
    ) -> None:
        self.model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        # SDK сам дописывает /v1beta/models, поэтому базовый адрес без этого пути.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                base_url=base_url,
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(
                    attempts=3,
                    initial_delay=0.5,
                    max_delay=4.0,
                ),
            ),
        )

    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[ContextMessage],
        user_message: str,
    ) -> str:
        """Отправляет system prompt, историю и новое сообщение пользователя."""
        contents = build_gemini_contents(history, user_message)
        if not contents:
            raise ServiceError("empty_message", "Пустое сообщение не отправляется.")
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self._temperature,
                    max_output_tokens=self._max_output_tokens,
                ),
            )
        except Exception as exc:
            self._raise_api_error(exc)
        text = self._read_text(response)
        if not text:
            raise ServiceError("empty_response", EMPTY_RESPONSE_MESSAGE)
        return text

    def _read_text(self, response: Any) -> str:
        try:
            raw = response.text
        except ValueError:
            return ""
        if not isinstance(raw, str):
            return ""
        return raw.strip()

    def _raise_api_error(self, exc: Exception) -> None:
        code = "api_unavailable" if is_transient(exc) else "api_error"
        status = getattr(exc, "code", None)
        logger.warning(
            "Запрос к Gemini завершился ошибкой",
            extra={
                "context": {
                    "error_type": type(exc).__name__,
                    "status": status,
                    "model": self.model,
                }
            },
        )
        raise ServiceError(code, FALLBACK_MESSAGE, {"error_type": type(exc).__name__}) from exc
