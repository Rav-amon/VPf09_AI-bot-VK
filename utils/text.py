"""Чистые функции для текста сообщений ВКонтакте."""

from __future__ import annotations

MAX_USER_TEXT_LENGTH = 4000
VK_MESSAGE_LIMIT = 4000
MIN_SPLIT_RATIO = 2


def validate_user_text(text: str) -> str | None:
    """Проверяет пустой текст и превышение лимита. None означает, что текст годится."""
    cleaned = text.strip()
    if not cleaned:
        return "Пустое сообщение не отправляется. Напишите вопрос текстом."
    if len(cleaned) > MAX_USER_TEXT_LENGTH:
        return (
            f"Сообщение длиннее {MAX_USER_TEXT_LENGTH} символов. "
            "Сократите текст и отправьте ещё раз."
        )
    return None


def clip(text: str, limit: int) -> str:
    """Обрезает подпись кнопки до лимита VK, не ломая смысл целиком."""
    compact = " ".join(text.split())
    if limit < 1:
        return ""
    if len(compact) <= limit:
        return compact
    if limit == 1:
        return compact[:1]
    return compact[: limit - 1] + "…"


def split_vk_text(text: str, limit: int = VK_MESSAGE_LIMIT) -> list[str]:
    """Делит длинный ответ на части не длиннее лимита сообщения VK."""
    cleaned = text.strip()
    if not cleaned:
        return ["Пустой ответ."]
    if len(cleaned) <= limit:
        return [cleaned]

    chunks: list[str] = []
    rest = cleaned
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        window = rest[:limit]
        cut = window.rfind("\n")
        if cut < limit // MIN_SPLIT_RATIO:
            cut = window.rfind(" ")
        if cut < limit // MIN_SPLIT_RATIO:
            cut = limit
        piece = rest[:cut].strip()
        if not piece:
            piece = rest[:limit]
            cut = limit
        chunks.append(piece)
        rest = rest[cut:].strip()
    return chunks
