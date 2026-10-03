"""Имена экранов и команд кнопок. Общие для клавиатур и обработчиков."""

from __future__ import annotations


class Screen:
    """Идентификаторы экранов, которые рисует слой VK."""

    MAIN = "main"
    HELP = "help"
    DIALOGS = "dialogs"
    DIALOG = "dialog"
    SETTINGS = "settings"
    ROLES = "roles"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class Cmd:
    """Команды в payload кнопок. Короткие латинские ключи укладываются в 255 байт."""

    MAIN = "main"
    HELP = "help"
    NEW_DIALOG = "new_dialog"
    LIST_DIALOGS = "list_dialogs"
    OPEN_DIALOG = "open_dialog"
    SETTINGS = "settings"
    ROLES = "roles"
    SET_ROLE = "set_role"
    DELETE_ASK = "delete_ask"
    DELETE = "delete_dialog"
    RENAME_ASK = "rename_ask"
    CLEAR_ASK = "clear_ask"
    CLEAR = "clear_history"
