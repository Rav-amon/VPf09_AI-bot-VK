"""Сборка зависимостей. VK-бот получает уже готовые сервисы."""

from __future__ import annotations

import logging

from vkbottle import Bot

from bot.handlers import register_handlers
from config.settings import Settings
from services.ai_service import AIService
from services.assistant import AssistantApp
from services.chat_service import ChatService
from services.dialog_service import DialogService
from services.memory_service import MemoryService
from services.providers import create_provider
from storage.json_user_storage import JsonUserStorage

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    """Собирает хранилище, модель и обработчики. Токен остаётся в настройках."""
    storage = JsonUserStorage(settings.users_dir)
    memory = MemoryService()
    dialogs = DialogService(storage, memory)
    ai = AIService(create_provider(settings))
    chat = ChatService(dialogs, memory, ai)
    app = AssistantApp(dialogs, chat, ai)
    bot = Bot(token=settings.vk_token)
    register_handlers(bot, app)
    logger.info(
        "Бот собран",
        extra={"context": {"model": settings.gemini_model, "provider": settings.ai_provider}},
    )
    return bot
