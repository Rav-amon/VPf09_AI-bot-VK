"""Состояния сценария, которые живут только в процессе бота."""

from __future__ import annotations

from vkbottle import BaseStateGroup


class FlowStates(BaseStateGroup):
    """Ожидание нового названия диалога."""

    RENAME_DIALOG = "rename_dialog"
