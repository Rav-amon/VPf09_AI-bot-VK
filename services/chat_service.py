"""Связка памяти, диалога и модели. Слой VK сюда не входит."""

from __future__ import annotations

import logging
import time

from models.records import UserRecord, active_dialog
from models.roles import get_role
from services.ai_service import AIService
from services.dialog_service import DialogService
from services.memory_service import MemoryService
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

MIN_AI_INTERVAL_SECONDS = 1.0


class ChatService:
    """Формирует контекст активного диалога и сохраняет удачный обмен."""

    def __init__(
        self,
        dialogs: DialogService,
        memory: MemoryService,
        ai: AIService,
    ) -> None:
        self._dialogs = dialogs
        self._memory = memory
        self._ai = ai
        self._last_call: dict[int, float] = {}

    async def answer(self, user_id: int, text: str) -> str:
        """Отвечает в активном диалоге. При ошибке модели история не меняется."""
        await self._dialogs.ensure_user(user_id)
        self._guard_interval(user_id)

        async def mutate(record: UserRecord) -> str:
            dialog = active_dialog(record)
            history = self._memory.build_context(dialog.messages)
            role = get_role(dialog.role)
            reply = await self._ai.complete(
                system_prompt=role.prompt,
                history=history,
                user_message=text,
            )
            await self._dialogs.remember_exchange(record, text.strip(), reply)
            return reply

        try:
            reply = await self._dialogs.update(user_id, mutate)
        except ServiceError:
            self._last_call.pop(user_id, None)
            raise
        logger.info(
            "Ответ модели сохранён",
            extra={"context": {"user_id": user_id, "model": self._ai.model_name}},
        )
        return reply

    def _guard_interval(self, user_id: int) -> None:
        now = time.monotonic()
        previous = self._last_call.get(user_id)
        if previous is not None and now - previous < MIN_AI_INTERVAL_SECONDS:
            raise ServiceError(
                "rate_limited",
                "Слишком часто. Подождите секунду и отправьте сообщение ещё раз.",
            )
        self._last_call[user_id] = now
