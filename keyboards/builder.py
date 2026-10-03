"""Клавиатуры VKBottle 4.11. Кнопки крепятся к сообщению и видны в диалоге."""

from __future__ import annotations

import json

from vkbottle import Keyboard, KeyboardButtonColor, Text

from models.commands import Cmd, Screen
from models.roles import list_roles
from models.screen import ScreenResponse
from utils.text import clip

LABEL_LIMIT = 40
PAYLOAD_LIMIT = 255


def _action(label: str, payload: dict[str, object]) -> Text:
    """Текст кнопки и payload строкой: так его принимает VK."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > PAYLOAD_LIMIT:
        raise ValueError("Payload кнопки больше 255 байт")
    title = clip(label, LABEL_LIMIT) or "Кнопка"
    return Text(title, raw)


def _add(
    keyboard: Keyboard,
    label: str,
    payload: dict[str, object],
    color: KeyboardButtonColor,
) -> None:
    """Добавляет кнопку вместе с цветом. Без цвета VK не показывает клавиатуру."""
    keyboard.add(_action(label, payload), color=color)


def main_menu_keyboard(role_id: str = "") -> str:
    """Кнопки под сообщением: действия и пять режимов общения."""
    keyboard = Keyboard(one_time=False, inline=True)
    _add(keyboard, "Новый диалог", {"cmd": Cmd.NEW_DIALOG}, KeyboardButtonColor.POSITIVE)
    _add(keyboard, "Список диалогов", {"cmd": Cmd.LIST_DIALOGS}, KeyboardButtonColor.PRIMARY)
    keyboard.row()
    _add(keyboard, "Настройки", {"cmd": Cmd.SETTINGS}, KeyboardButtonColor.SECONDARY)
    _add(keyboard, "Помощь", {"cmd": Cmd.HELP}, KeyboardButtonColor.SECONDARY)
    roles = list_roles()
    # Два режима в ряд: вместе с меню это 5 рядов и 9 кнопок, лимит VK — 6 и 10.
    for index, role in enumerate(roles):
        if index % 2 == 0:
            keyboard.row()
        current = role.id == role_id
        label = f"✓ {role.title}" if current else role.title
        color = KeyboardButtonColor.POSITIVE if current else KeyboardButtonColor.SECONDARY
        _add(keyboard, label, {"cmd": Cmd.SET_ROLE, "role": role.id}, color)
    return keyboard.get_json()


def _dialogs_keyboard(response: ScreenResponse) -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    for dialog in response.dialogs:
        title = f"✓ {dialog.title}" if dialog.is_active else dialog.title
        _add(
            keyboard,
            title,
            {"cmd": Cmd.OPEN_DIALOG, "id": dialog.id},
            KeyboardButtonColor.POSITIVE,
        )
        _add(
            keyboard,
            "Удалить",
            {"cmd": Cmd.DELETE_ASK, "id": dialog.id},
            KeyboardButtonColor.NEGATIVE,
        )
        keyboard.row()
    if response.total_pages > 1 and response.page > 0:
        _add(
            keyboard,
            "Назад",
            {"cmd": Cmd.LIST_DIALOGS, "page": response.page - 1},
            KeyboardButtonColor.SECONDARY,
        )
    if response.total_pages > 1 and response.page < response.total_pages - 1:
        _add(
            keyboard,
            "Дальше",
            {"cmd": Cmd.LIST_DIALOGS, "page": response.page + 1},
            KeyboardButtonColor.SECONDARY,
        )
    if response.total_pages > 1:
        keyboard.row()
    _add(keyboard, "В меню", {"cmd": Cmd.MAIN}, KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def _dialog_keyboard(response: ScreenResponse) -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    _add(
        keyboard,
        "Переименовать",
        {"cmd": Cmd.RENAME_ASK, "id": response.dialog_id},
        KeyboardButtonColor.PRIMARY,
    )
    keyboard.row()
    _add(
        keyboard,
        "Удалить",
        {"cmd": Cmd.DELETE_ASK, "id": response.dialog_id},
        KeyboardButtonColor.NEGATIVE,
    )
    keyboard.row()
    _add(keyboard, "К списку", {"cmd": Cmd.LIST_DIALOGS}, KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def _settings_keyboard() -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    _add(keyboard, "Сменить режим", {"cmd": Cmd.ROLES}, KeyboardButtonColor.PRIMARY)
    keyboard.row()
    _add(keyboard, "Очистить историю", {"cmd": Cmd.CLEAR_ASK}, KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    _add(keyboard, "В меню", {"cmd": Cmd.MAIN}, KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def _confirm_keyboard(response: ScreenResponse) -> str:
    yes_payload: dict[str, object] = {"cmd": response.confirm_cmd}
    if response.dialog_id:
        yes_payload["id"] = response.dialog_id
    if response.confirm_cmd == Cmd.DELETE:
        yes_label = "Да, удалить"
        no_payload: dict[str, object] = {"cmd": Cmd.LIST_DIALOGS}
    else:
        yes_label = "Да, очистить"
        no_payload = {"cmd": Cmd.SETTINGS}
    keyboard = Keyboard(one_time=False, inline=True)
    _add(keyboard, yes_label, yes_payload, KeyboardButtonColor.NEGATIVE)
    _add(keyboard, "Отмена", no_payload, KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def _cancel_keyboard(response: ScreenResponse) -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    _add(
        keyboard,
        "Отмена",
        {"cmd": Cmd.OPEN_DIALOG, "id": response.dialog_id},
        KeyboardButtonColor.SECONDARY,
    )
    return keyboard.get_json()


def render_keyboard(response: ScreenResponse) -> str:
    """Выбирает клавиатуру экрана. Кнопки стоят под текстом сообщения."""
    if response.screen in {Screen.MAIN, Screen.HELP, Screen.ROLES}:
        return main_menu_keyboard(response.role_id)
    if response.screen == Screen.DIALOGS:
        return _dialogs_keyboard(response)
    if response.screen == Screen.DIALOG:
        return _dialog_keyboard(response)
    if response.screen == Screen.SETTINGS:
        return _settings_keyboard()
    if response.screen == Screen.CONFIRM:
        return _confirm_keyboard(response)
    if response.screen == Screen.CANCEL:
        return _cancel_keyboard(response)
    return main_menu_keyboard(response.role_id)
