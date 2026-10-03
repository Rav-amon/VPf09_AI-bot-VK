"""Данные экрана, которые сервис отдаёт слою клавиатур."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DialogView:
    """Краткая карточка диалога для списка и кнопок."""

    id: str
    title: str
    role_id: str
    role_title: str
    is_active: bool
    message_count: int


@dataclass(frozen=True, slots=True)
class ScreenResponse:
    """Готовый текст и параметры экрана. VK-клавиатуру собирает другой слой."""

    text: str
    screen: str
    dialogs: tuple[DialogView, ...] = ()
    page: int = 0
    total_pages: int = 1
    dialog_id: str = ""
    role_id: str = ""
    confirm_cmd: str = ""
