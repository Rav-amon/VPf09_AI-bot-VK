"""Обработчики личных сообщений. Они показывают экраны и не вызывают модель напрямую."""

from __future__ import annotations

import logging
from typing import Any
from collections.abc import Awaitable

from vkbottle import Bot
from vkbottle.bot import Message

from bot.delivery import deliver_thinking, send_text
from bot.states import FlowStates
from keyboards.builder import render_keyboard
from models.commands import Cmd, Screen
from models.screen import ScreenResponse
from services.assistant import AssistantApp
from utils.errors import ServiceError
from utils.text import validate_user_text

logger = logging.getLogger(__name__)

MENU_COMMANDS = {
    "начать": "main",
    "/start": "main",
    "start": "main",
    "старт": "main",
    "меню": "main",
    "помощь": "help",
    "/help": "help",
    "отмена": "cancel",
}


def read_user_id(message: Message) -> int | None:
    """Берёт идентификатор пользователя. Сообщения сообществ пропускаются."""
    user_id = message.from_id
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return None
    return user_id


def read_payload(message: Message) -> dict[str, Any]:
    """Разбирает payload кнопки. У обычного текста его нет."""
    raw = message.get_payload_json()
    if isinstance(raw, dict):
        return raw
    return {}


def is_plain_message(message: Message) -> bool:
    """Обычный текст, а не нажатие кнопки."""
    return message.payload is None


def menu_action(text: str) -> str | None:
    """Короткое слово из меню. Внутри фразы оно не перехватывается."""
    return MENU_COMMANDS.get(text.strip().lower())


def read_page(payload: dict[str, Any]) -> int:
    raw = payload.get("page", 0)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    return value


async def clear_state(bot: Bot, message: Message) -> None:
    if message.state_peer is None:
        return
    await bot.state_dispenser.delete(message.peer_id)


async def show(message: Message, response: ScreenResponse) -> None:
    await send_text(message, response.text, render_keyboard(response))


def register_handlers(bot: Bot, app: AssistantApp) -> None:
    """Регистрирует обработчики. Первый подходящий блокирует остальные."""

    @bot.on.private_message(func=lambda message: message.payload is not None)
    async def on_button(message: Message) -> None:
        user_id = read_user_id(message)
        if user_id is None:
            return
        await clear_state(bot, message)
        payload = read_payload(message)
        command = str(payload.get("cmd", ""))
        if command == Cmd.RENAME_ASK:
            response = await safe_screen(app.ask_rename(user_id, str(payload.get("id", ""))))
            if response.screen == Screen.CANCEL:
                await bot.state_dispenser.set(
                    message.peer_id,
                    FlowStates.RENAME_DIALOG,
                    dialog_id=response.dialog_id,
                )
            await show(message, response)
            return
        response = await safe_screen(route_command(app, user_id, payload))
        await show(message, response)

    @bot.on.private_message(func=lambda message: is_plain_message(message) and bool(menu_action(message.text or "")))
    async def on_menu_word(message: Message) -> None:
        user_id = read_user_id(message)
        if user_id is None:
            return
        action = menu_action(message.text or "")
        dialog_id = ""
        if message.state_peer is not None:
            dialog_id = str(message.state_peer.payload.get("dialog_id", ""))
        await clear_state(bot, message)
        if action == "cancel" and dialog_id:
            response = await safe_screen(app.open_dialog(user_id, dialog_id))
        elif action == "help":
            response = await safe_screen(app.open_help(user_id))
        else:
            response = await safe_screen(app.open_main(user_id))
        await show(message, response)

    @bot.on.private_message(state=FlowStates.RENAME_DIALOG, func=is_plain_message)
    async def on_rename(message: Message) -> None:
        user_id = read_user_id(message)
        if user_id is None:
            return
        dialog_id = ""
        if message.state_peer is not None:
            dialog_id = str(message.state_peer.payload.get("dialog_id", ""))
        try:
            response = await app.rename(user_id, dialog_id, message.text or "")
        except ServiceError as exc:
            await send_text(
                message,
                exc.message,
                render_keyboard(ScreenResponse(text="", screen=Screen.CANCEL, dialog_id=dialog_id)),
            )
            return
        await clear_state(bot, message)
        await show(message, response)

    @bot.on.private_message(state=None, func=is_plain_message)
    async def on_chat(message: Message) -> None:
        user_id = read_user_id(message)
        if user_id is None:
            return
        text = message.text or ""
        opened = await safe_screen(app.open_main(user_id))
        keyboard = render_keyboard(opened)
        problem = validate_user_text(text)
        if message.attachments and not text.strip():
            problem = "Я пока понимаю только текстовые сообщения. Напишите вопрос словами."
        if problem:
            await show(
                message,
                ScreenResponse(text=problem, screen=Screen.MAIN, role_id=opened.role_id),
            )
            return

        async def produce() -> str:
            response = await app.ask(user_id, text)
            return response.text

        await deliver_thinking(message, produce, keyboard)


async def route_command(app: AssistantApp, user_id: int, payload: dict[str, Any]) -> ScreenResponse:
    """Переводит команду кнопки в сценарий приложения."""
    command = str(payload.get("cmd", ""))
    dialog_id = str(payload.get("id", ""))
    role_id = str(payload.get("role", ""))
    page = read_page(payload)
    if command == Cmd.MAIN:
        return await app.open_main(user_id)
    if command == Cmd.HELP:
        return await app.open_help(user_id)
    if command == Cmd.NEW_DIALOG:
        return await app.create_dialog(user_id)
    if command == Cmd.LIST_DIALOGS:
        return await app.open_dialogs(user_id, page)
    if command == Cmd.OPEN_DIALOG:
        return await app.open_dialog(user_id, dialog_id)
    if command == Cmd.SETTINGS:
        return await app.open_settings(user_id)
    if command == Cmd.ROLES:
        return await app.open_roles(user_id)
    if command == Cmd.SET_ROLE:
        return await app.set_role(user_id, role_id)
    if command == Cmd.DELETE_ASK:
        return await app.ask_delete(user_id, dialog_id)
    if command == Cmd.DELETE:
        return await app.delete_dialog(user_id, dialog_id)
    if command == Cmd.CLEAR_ASK:
        return await app.ask_clear(user_id)
    if command == Cmd.CLEAR:
        return await app.clear_history(user_id, dialog_id)
    logger.info("Неизвестная команда кнопки", extra={"context": {"cmd": command}})
    return await app.open_main(user_id)


async def safe_screen(awaitable: Awaitable[ScreenResponse]) -> ScreenResponse:
    """Превращает сбой хранилища в сообщение, чтобы бот не замолчал."""
    try:
        return await awaitable
    except ServiceError as exc:
        logger.warning(
            "Сценарий завершился ошибкой",
            extra={"context": {"code": exc.code}},
        )
        return ScreenResponse(text=exc.message, screen=Screen.MAIN)
    except Exception:
        logger.exception("Необработанная ошибка сценария")
        return ScreenResponse(
            text="Произошла внутренняя ошибка. Попробуйте ещё раз.",
            screen=Screen.MAIN,
        )
