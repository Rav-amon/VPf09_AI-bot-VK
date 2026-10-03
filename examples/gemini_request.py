"""Пример запроса к Gemini через ProxyAPI тем же провайдером, что использует бот.

Запуск из корня проекта:
    .venv\\Scripts\\python examples\\gemini_request.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import load_settings
from models.records import ContextMessage
from services.providers.gemini import GeminiProvider
from utils.errors import ServiceError


async def main() -> None:
    """Отправляет system prompt, одну реплику истории и новый вопрос."""
    settings = load_settings(ROOT)
    provider = GeminiProvider(
        api_key=settings.proxy_api_key,
        model=settings.gemini_model,
        base_url=settings.gemini_base_url,
        temperature=settings.temperature,
        max_output_tokens=settings.max_output_tokens,
        timeout_ms=settings.request_timeout_ms,
    )
    answer = await provider.complete(
        system_prompt="Отвечай по-русски одним коротким предложением.",
        history=[
            ContextMessage(role="user", content="Меня зовут Алекс."),
            ContextMessage(role="assistant", content="Приятно познакомиться, Алекс."),
        ],
        user_message="Как меня зовут?",
    )
    print(answer)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ServiceError as exc:
        print(exc.message)
        raise SystemExit(1) from exc
