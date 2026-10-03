"""Отправка текста, имитация набора и статус «бот думает»."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from vkbottle.bot import Message

from utils.text import split_vk_text

logger = logging.getLogger(__name__)

THINKING_TEXT = "Бот думает…"
TYPING_REFRESH_SECONDS = 4
RANDOM_ID_LIMIT = 2_000_000_000


def next_random_id() -> int:
    """Уникальный random_id: VK отбрасывает повтор с тем же значением."""
    return secrets.randbelow(RANDOM_ID_LIMIT) + 1


async def keep_typing(api: object, peer_id: int, stop: asyncio.Event) -> None:
    """Периодически шлёт messages.setActivity, пока модель готовит ответ."""
    messages = getattr(getattr(api, "messages", None), "set_activity", None)
    if messages is None:
        return
    while not stop.is_set():
        try:
            await messages(peer_id=peer_id, type="typing")
        except Exception:
            logger.warning(
                "Не удалось показать статус набора текста",
                extra={"context": {"peer_id": peer_id}},
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=TYPING_REFRESH_SECONDS)
        except TimeoutError:
            continue


async def send_with_keyboard(message: Message, text: str, keyboard: str | None) -> int:
    """Отправляет сообщение через peer_id. У peer_ids ВКонтакте не показывает клавиатуру."""
    params: dict[str, Any] = {
        "peer_id": message.peer_id,
        "message": text,
        "random_id": next_random_id(),
    }
    if keyboard:
        params["keyboard"] = keyboard
    raw = await message.ctx_api.request("messages.send", params)
    sent = raw.get("response", raw) if isinstance(raw, dict) else raw
    if isinstance(sent, int):
        return sent
    if isinstance(sent, dict) and "message_id" in sent:
        return int(sent["message_id"])
    logger.warning(
        "ВКонтакте вернул ответ без идентификатора сообщения",
        extra={"context": {"peer_id": message.peer_id}},
    )
    return 0


async def send_text(message: Message, text: str, keyboard: str) -> None:
    """Отправляет текст частями. Клавиатура крепится к последней части."""
    parts = split_vk_text(text)
    last_index = len(parts) - 1
    for index, part in enumerate(parts):
        await send_with_keyboard(
            message,
            part,
            keyboard if index == last_index else None,
        )


async def deliver_thinking(
    message: Message,
    producer: Callable[[], Awaitable[str]],
    keyboard: str,
) -> None:
    """Показывает набор текста и заменяет «Бот думает…» готовым ответом."""
    stop = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(message.ctx_api, message.peer_id, stop))
    placeholder_id = await send_with_keyboard(message, THINKING_TEXT, keyboard)
    try:
        text = await producer()
    except Exception:
        logger.exception(
            "Не удалось подготовить ответ",
            extra={"context": {"peer_id": message.peer_id}},
        )
        text = "Произошла внутренняя ошибка. Попробуйте ещё раз."
    finally:
        stop.set()
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task

    parts = split_vk_text(str(text))
    await _replace_placeholder(message, placeholder_id, parts, keyboard)


async def _replace_placeholder(
    message: Message,
    message_id: int,
    parts: list[str],
    keyboard: str,
) -> None:
    first_keyboard = keyboard if len(parts) == 1 else None
    try:
        await message.ctx_api.messages.edit(
            peer_id=message.peer_id,
            message_id=message_id,
            message=parts[0],
            keyboard=first_keyboard,
        )
    except Exception:
        logger.warning(
            "Не удалось заменить статус, отправляю отдельное сообщение",
            extra={"context": {"peer_id": message.peer_id}},
        )
        with contextlib.suppress(Exception):
            await message.ctx_api.messages.delete(
                message_ids=[message_id],
                delete_for_all=True,
            )
        await send_with_keyboard(message, parts[0], first_keyboard)
    last_extra = len(parts) - 2
    for index, part in enumerate(parts[1:]):
        await send_with_keyboard(
            message,
            part,
            keyboard if index == last_extra else None,
        )
