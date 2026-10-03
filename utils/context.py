"""Сборка контекста диалога для модели."""

from __future__ import annotations

from models.records import ContextMessage

# В Gemini роль ответа модели называется model, а в нашей памяти — assistant.
GEMINI_ASSISTANT_ROLE = "model"
GEMINI_USER_ROLE = "user"


def normalize_turns(messages: list[ContextMessage]) -> list[ContextMessage]:
    """Убирает пустые реплики, склеивает одинаковые роли и начинает историю с user."""
    cleaned = [
        ContextMessage(role=item.role, content=item.content.strip())
        for item in messages
        if item.content.strip() and item.role in {"user", "assistant"}
    ]
    while cleaned and cleaned[0].role != "user":
        cleaned.pop(0)

    merged: list[ContextMessage] = []
    for item in cleaned:
        if merged and merged[-1].role == item.role:
            merged[-1] = ContextMessage(
                role=item.role,
                content=f"{merged[-1].content}\n{item.content}",
            )
            continue
        merged.append(item)
    return merged


def to_gemini_roles(messages: list[ContextMessage]) -> list[dict[str, str]]:
    """Переводит внутренние роли в роли запроса Gemini: user и model."""
    result: list[dict[str, str]] = []
    for item in normalize_turns(messages):
        role = GEMINI_ASSISTANT_ROLE if item.role == "assistant" else GEMINI_USER_ROLE
        result.append({"role": role, "content": item.content})
    return result
